"""CLAUDE.md §6 drift guard: files are published only through shared_library.atomic_files.

A direct ``os.replace`` / ``os.rename`` in src/ is a second, hand-maintained copy of the atomic-write
protocol (unique tmp, fsync, directory fsync, cleanup on error). ZERO-gate.
"""

from __future__ import annotations

import ast

from _scan import Hit, SymbolWalker, source_files

_FORBIDDEN = frozenset({"replace", "rename"})


class _RenameScanner(SymbolWalker):
    def __init__(self, rel_path: str) -> None:
        super().__init__()
        self.rel_path = rel_path
        self.hits: list[Hit] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in _FORBIDDEN
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
        ):
            self.hits.append(Hit(self.rel_path, node.lineno, self.symbol, f"os.{func.attr}()"))
        self.generic_visit(node)


def scan_renames(tree: ast.Module, rel_path: str) -> list[Hit]:
    scanner = _RenameScanner(rel_path)
    scanner.visit(tree)
    return scanner.hits


def test_src_never_renames_files_directly() -> None:
    hits = [h for rel, tree in source_files() for h in scan_renames(tree, rel)]
    assert hits == [], f"use shared_library.atomic_files.atomic_replace instead (CLAUDE.md §6): {hits}"


def test_guard_flags_planted_violations() -> None:
    planted = ast.parse("import os\ndef a(p, q):\n    os.replace(p, q)\ndef b(p, q):\n    os.rename(p, q)\n")
    assert [h.symbol for h in scan_renames(planted, "p.py")] == ["a", "b"]


def test_guard_ignores_str_replace() -> None:
    assert scan_renames(ast.parse("def a(s):\n    return s.replace('a', 'b')\n"), "ok.py") == []
