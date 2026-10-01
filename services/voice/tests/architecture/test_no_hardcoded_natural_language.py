"""CLAUDE.md §4 guard (voice has a natural-language surface): no linguistic regex, no word lists.

Flags: regex pattern literals with \\b / [a-z] / [A-Z]; `re` imported in the prose-handling modules
(text_normalizer, script_builder); `.split()` inside `len(...)` (word counting); list/set/tuple
literals holding 3 or more lowercase alphabetic string words (keyword/stopword lists). Type-annotation
subscripts (Literal[...]) are exempt. _ALLOWLIST is by exact (rel_path, symbol). ZERO-gate.
"""

from __future__ import annotations

import ast

from _scan import Hit, SymbolWalker, source_files

_PROSE_MODULES = frozenset({"services/text_normalizer.py", "services/script_builder.py"})
_REGEX_FORBIDDEN_FRAGMENTS = ("\\b", "[a-z]", "[A-Z]", "[a-zA-Z]")
_MIN_WORDS = 3

# Empty by design. BLOCK_POLICY is a dict of DeepSeek-OCR protocol labels (a closed model
# vocabulary, not prose) and dict literals are lookup tables this guard does not treat as word lists.
_ALLOWLIST: frozenset[tuple[str, str]] = frozenset()


def _word(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.isalpha() and node.value.islower()


class _NlScanner(SymbolWalker):
    def __init__(self, rel_path: str, allowlist: frozenset[tuple[str, str]]) -> None:
        super().__init__()
        self.rel_path = rel_path
        self.allowlist = allowlist
        self.hits: list[Hit] = []
        self._annotation_nodes: set[int] = set()

    def _flag(self, node: ast.AST, detail: str) -> None:
        if (self.rel_path, self.symbol) not in self.allowlist:
            self.hits.append(Hit(self.rel_path, node.lineno, self.symbol, detail))  # type: ignore[attr-defined]

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self._annotation_nodes.update(id(n) for n in ast.walk(node.slice))
        self.generic_visit(node)

    def _check_collection(self, node: ast.AST, elements: list[ast.expr]) -> None:
        if id(node) not in self._annotation_nodes and sum(_word(e) for e in elements) >= _MIN_WORDS:
            self._flag(node, "literal of lowercase words (keyword list)")

    def visit_List(self, node: ast.List) -> None:
        self._check_collection(node, node.elts)
        self.generic_visit(node)

    visit_Set = visit_Tuple = visit_List  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id == "len":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr == "split":
                    self._flag(node, "len(... .split()) word counting")
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "re":
            for arg in node.args[:1]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if any(fragment in arg.value for fragment in _REGEX_FORBIDDEN_FRAGMENTS):
                        self._flag(node, "linguistic regex pattern")
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        if self.rel_path in _PROSE_MODULES and any(alias.name == "re" for alias in node.names):
            self._flag(node, "re imported in a prose-handling module")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.rel_path in _PROSE_MODULES and node.module == "re":
            self._flag(node, "re imported in a prose-handling module")


def scan_language(source: str, rel_path: str, allowlist: frozenset[tuple[str, str]]) -> list[Hit]:
    scanner = _NlScanner(rel_path, allowlist)
    scanner.visit(ast.parse(source))
    return scanner.hits


def test_no_hardcoded_natural_language_in_src() -> None:
    hits = [h for rel, tree in _trees() for h in _hits(tree, rel, _ALLOWLIST)]
    assert hits == [], f"hardcoded natural language (CLAUDE.md §4): {hits}"


def _trees():
    return source_files()


def _hits(tree: ast.Module, rel: str, allowlist: frozenset[tuple[str, str]]) -> list[Hit]:
    scanner = _NlScanner(rel, allowlist)
    scanner.visit(tree)
    return scanner.hits


def test_allowlist_entries_are_live() -> None:
    unfiltered = {(h.rel_path, h.symbol) for rel, tree in _trees() for h in _hits(tree, rel, frozenset())}
    assert unfiltered == set(_ALLOWLIST)


def test_dict_literals_are_not_word_lists() -> None:
    assert scan_language('POLICY = {"title": 1, "text": 2, "image": 3}\n', "services/x.py", frozenset()) == []


def test_guard_flags_planted_violations() -> None:
    planted = '''
import re
STOP = ["the", "a", "of"]
KEYS = {"alpha", "beta", "gamma"}
def f(text):
    return len(text.split())
def g(text):
    return re.compile(r"\\bword\\b").findall(text)
def h(text):
    return re.search("[a-z]+", text)
'''
    details = [h.detail for h in scan_language(planted, "services/text_normalizer.py", frozenset())]
    assert details.count("literal of lowercase words (keyword list)") == 2
    assert details.count("len(... .split()) word counting") == 1
    assert details.count("linguistic regex pattern") == 2
    assert details.count("re imported in a prose-handling module") == 1


def test_guard_accepts_structural_code() -> None:
    structural = '''
from typing import Literal
Kind = Literal["created", "rebuilt", "unchanged"]
PAIRS = (("a", "b"), ("c", "d"))
def f(x: str) -> list[str]:
    return x.split(",")
'''
    assert scan_language(structural, "services/other.py", frozenset()) == []


def test_re_is_importable_outside_prose_modules() -> None:
    assert scan_language("import re\n", "services/other.py", frozenset()) == []
