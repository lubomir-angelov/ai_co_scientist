"""CLAUDE.md §7 guard: no length-capped slice / textwrap.shorten / .truncate() / str(...)[:N] preview.

Any slice with an UPPER bound that is not len(...) is flagged, as is a tail slice with a negative
constant lower bound below -1 and no upper bound (``x[-200:]``) and any ``islice`` call (strict: no
assigned/returned/logged context judgement). ``x[-1:]`` (the last element) stays allowed. _ALLOWLIST is the SSOT of reviewed windowing sites by exact (rel_path, symbol).
ZERO-gate.
"""

from __future__ import annotations

import ast

from _scan import Hit, SymbolWalker, source_files

# pack_phoneme_windows is the named windowing helper: it PARTITIONS the stream (nothing dropped),
# asserted by its own lossless-partition invariant and test.
_ALLOWLIST: frozenset[tuple[str, str]] = frozenset({("services/phoneme_windows.py", "pack_phoneme_windows")})


def _is_len_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len"


def _negative_constant(node: ast.expr | None) -> int | None:
    """The int value of a literal negative bound such as ``-200``, else None."""
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, int)
    ):
        return -node.operand.value
    return None


class _TruncationScanner(SymbolWalker):
    def __init__(self, rel_path: str, allowlist: frozenset[tuple[str, str]]) -> None:
        super().__init__()
        self.rel_path = rel_path
        self.allowlist = allowlist
        self.hits: list[Hit] = []

    def _flag(self, node: ast.AST, detail: str) -> None:
        if (self.rel_path, self.symbol) not in self.allowlist:
            self.hits.append(Hit(self.rel_path, node.lineno, self.symbol, detail))  # type: ignore[attr-defined]

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.slice, ast.Slice) and node.slice.upper is not None and not _is_len_call(node.slice.upper):
            self._flag(node, "length-capped slice")
        if isinstance(node.slice, ast.Slice) and node.slice.upper is None:
            lower = _negative_constant(node.slice.lower)
            if lower is not None and abs(lower) > 1:
                self._flag(node, "length-capped tail slice")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {"shorten", "truncate"}:
            self._flag(node, f"{func.attr}()")
        callee = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if callee == "islice":
            self._flag(node, "islice()")
        self.generic_visit(node)


def scan_truncation(source: str, rel_path: str, allowlist: frozenset[tuple[str, str]]) -> list[Hit]:
    return _scan_tree(ast.parse(source), rel_path, allowlist)


def _scan_tree(tree: ast.Module, rel: str, allowlist: frozenset[tuple[str, str]]) -> list[Hit]:
    scanner = _TruncationScanner(rel, allowlist)
    scanner.visit(tree)
    return scanner.hits


def test_no_truncation_in_src() -> None:
    hits = [h for rel, tree in source_files() for h in _scan_tree(tree, rel, _ALLOWLIST)]
    assert hits == [], f"truncation (CLAUDE.md §7): {hits}"


def test_allowlist_entries_are_live() -> None:
    """Every allowlisted site must really contain a flagged construct (no stale entries)."""
    unfiltered = {(h.rel_path, h.symbol) for rel, tree in source_files() for h in _scan_tree(tree, rel, frozenset())}
    assert unfiltered == set(_ALLOWLIST)


def test_guard_flags_planted_violations() -> None:
    planted = """
import textwrap
def a(x):
    return x[:80]
def b(x):
    return str(x)[:10]
def c(x):
    return repr(x)[0:5]
def d(x):
    return textwrap.shorten(x, 20)
def e(x):
    return x.truncate(3)
def f(x):
    return x[-200:]
def g(x):
    return list(islice(x, 5))
def h(x):
    return list(itertools.islice(x, 5))
"""
    assert [h.symbol for h in scan_truncation(planted, "p.py", frozenset())] == ["a", "b", "c", "d", "e", "f", "g", "h"]


def test_guard_accepts_open_ended_and_len_bounded_slices() -> None:
    assert scan_truncation("def f(x):\n    return x[1:], x[:len(x)], x[-1:]\n", "ok.py", frozenset()) == []


def test_allowlist_silences_exactly_its_symbol() -> None:
    planted = "def a(x):\n    return x[:3]\ndef b(x):\n    return x[:3]\n"
    assert [h.symbol for h in scan_truncation(planted, "p.py", frozenset({("p.py", "a")}))] == ["b"]
