"""CLAUDE.md §2 guard: no stand-in literal in a parameter / dataclass / pydantic Field default.

_DENYLIST is the single source of truth for the forbidden missing-data words. ZERO-gate.
"""

from __future__ import annotations

import ast

from _scan import Hit, SymbolWalker, source_files

_DENYLIST: frozenset[str] = frozenset(
    {
        "unknown", "placeholder", "tbd", "todo", "n/a", "na", "none", "null", "undefined", "default",
        "dummy", "fixme", "unspecified", "missing", "untitled", "anonymous", "xxx", "-", "?",
    }
)
# Exact (rel_path, symbol) of reviewed genuine closed-vocabulary uses. Empty by design.
_ALLOWLIST: frozenset[tuple[str, str]] = frozenset()
# pydantic's Field(...) and dataclasses' field(...) both declare a model/dataclass default.
_FIELD_CALLEES = frozenset({"Field", "field"})


def _is_denied(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.casefold() in _DENYLIST:
        return node.value
    return None


class _DefaultScanner(SymbolWalker):
    def __init__(self, rel_path: str) -> None:
        super().__init__()
        self.rel_path = rel_path
        self.hits: list[Hit] = []

    def _flag(self, node: ast.expr | None, line: int, where: str) -> None:
        word = _is_denied(node)
        if word is not None and (self.rel_path, self.symbol) not in _ALLOWLIST:
            self.hits.append(Hit(self.rel_path, line, self.symbol, f"{where} default {word!r}"))

    def _check_args(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            self._flag(default, node.lineno, "parameter")

    def _on_enter(self, node: ast.AST) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            self._check_args(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._flag(node.value, node.lineno, "field")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        callee = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
        if callee in _FIELD_CALLEES:
            if node.args:
                self._flag(node.args[0], node.lineno, "Field")
            for keyword in node.keywords:
                if keyword.arg == "default":
                    self._flag(keyword.value, node.lineno, "Field")
        self.generic_visit(node)


def scan_defaults(source: str, rel_path: str) -> list[Hit]:
    scanner = _DefaultScanner(rel_path)
    scanner.visit(ast.parse(source))
    return scanner.hits


class _CoalesceScanner(SymbolWalker):
    def __init__(self, rel_path: str) -> None:
        super().__init__()
        self.rel_path = rel_path
        self.hits: list[Hit] = []

    @staticmethod
    def _is_str_literal(node: ast.expr) -> bool:
        return isinstance(node, ast.Constant) and isinstance(node.value, str)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and len(node.args) == 2
            and self._is_str_literal(node.args[1])
        ):
            self.hits.append(Hit(self.rel_path, node.lineno, self.symbol, ".get(key, <str literal>)"))
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if isinstance(node.op, ast.Or) and any(self._is_str_literal(v) for v in node.values[1:]):
            self.hits.append(Hit(self.rel_path, node.lineno, self.symbol, "x or <str literal>"))
        self.generic_visit(node)


def scan_coalescing(source: str, rel_path: str) -> list[Hit]:
    scanner = _CoalesceScanner(rel_path)
    scanner.visit(ast.parse(source))
    return scanner.hits


def test_no_placeholder_defaults_in_src() -> None:
    hits = [h for rel, tree in source_files() for h in _scan_tree(tree, rel)]
    assert hits == [], f"placeholder defaults (CLAUDE.md §2): {hits}"


def _scan_tree(tree: ast.Module, rel: str) -> list[Hit]:
    scanner = _DefaultScanner(rel)
    scanner.visit(tree)
    return scanner.hits


def test_no_str_literal_coalescing_in_src() -> None:
    hits = []
    for rel, tree in source_files():
        scanner = _CoalesceScanner(rel)
        scanner.visit(tree)
        hits.extend(scanner.hits)
    assert hits == [], f".get/or stand-in coalescing (CLAUDE.md §1): {hits}"


def test_allowlist_is_empty() -> None:
    assert _ALLOWLIST == frozenset()


def test_guard_flags_planted_violations() -> None:
    planted = '''
from dataclasses import dataclass
from pydantic import BaseModel, Field

def f(name: str = "unknown", *, other: str = "TBD"): ...

@dataclass
class A:
    label: str = "placeholder"

class M(BaseModel):
    title: str = Field(default="n/a")
'''
    details = sorted(h.detail for h in scan_defaults(planted, "planted.py"))
    assert details == sorted(
        [
            "parameter default 'unknown'",
            "parameter default 'TBD'",
            "field default 'placeholder'",
            "Field default 'n/a'",
        ]
    )


def test_guard_flags_field_call_forms_and_reports_parameter_defaults_under_their_function() -> None:
    planted = '''
from dataclasses import dataclass, field
from pydantic import Field

@dataclass
class A:
    x: str = field(default="unknown")

class M:
    y: str = Field("unknown")

class K:
    def method(self, name: str = "tbd"): ...
'''
    assert sorted((h.symbol, h.detail) for h in scan_defaults(planted, "planted.py")) == sorted(
        [
            ("A", "Field default 'unknown'"),
            ("M", "Field default 'unknown'"),
            ("K.method", "parameter default 'tbd'"),
        ]
    )


def test_guard_accepts_honest_defaults() -> None:
    honest = 'def f(a: str | None = None, b: str = "", c: int = 3): ...'
    assert scan_defaults(honest, "ok.py") == []


def test_coalescing_guard_flags_planted_violations() -> None:
    planted = 'd = {}\nx = d.get("k", "unknown")\ny = d["k"] or "tbd"\nz = d.get("k", 0)\n'
    assert [h.detail for h in scan_coalescing(planted, "p.py")] == [".get(key, <str literal>)", "x or <str literal>"]
