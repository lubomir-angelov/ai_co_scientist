"""Shared helpers for the AST fitness guards (scan src/voice_service, report (rel_path, line, symbol))."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[2] / "src" / "voice_service"


@dataclass(frozen=True)
class Hit:
    rel_path: str
    line: int
    symbol: str
    detail: str


def source_files() -> Iterator[tuple[str, ast.Module]]:
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        yield path.relative_to(PACKAGE_DIR).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


class SymbolWalker(ast.NodeVisitor):
    """NodeVisitor that tracks the enclosing function/class symbol (module level = "<module>")."""

    def __init__(self) -> None:
        self._stack: list[str] = []

    @property
    def symbol(self) -> str:
        return ".".join(self._stack) if self._stack else "<module>"

    def _on_enter(self, node: ast.AST) -> None:
        """Hook run with the symbol already pushed, so findings on ``node`` carry its own name."""

    def _scoped(self, node: ast.AST, name: str) -> None:
        self._stack.append(name)
        self._on_enter(node)
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scoped(node, node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scoped(node, node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scoped(node, node.name)
