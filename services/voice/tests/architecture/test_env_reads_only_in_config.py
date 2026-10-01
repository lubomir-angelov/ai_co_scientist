"""CLAUDE.md §6 guard: the process environment is read ONLY in core/config.py. ZERO-gate."""

from __future__ import annotations

import ast

from _scan import Hit, SymbolWalker, source_files

_EXEMPT_FILES = frozenset({"core/config.py"})
_ALLOWLIST: frozenset[tuple[str, str]] = frozenset()
_ENV_ATTRS = frozenset({"environ", "getenv", "putenv", "unsetenv", "environb", "getenvb"})


class _EnvScanner(SymbolWalker):
    def __init__(self, rel_path: str) -> None:
        super().__init__()
        self.rel_path = rel_path
        self.hits: list[Hit] = []

    def _flag(self, node: ast.AST, detail: str) -> None:
        if (self.rel_path, self.symbol) not in _ALLOWLIST:
            self.hits.append(Hit(self.rel_path, node.lineno, self.symbol, detail))  # type: ignore[attr-defined]

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _ENV_ATTRS and isinstance(node.value, ast.Name) and node.value.id == "os":
            self._flag(node, f"os.{node.attr}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "os" and any(alias.name in _ENV_ATTRS for alias in node.names):
            self._flag(node, "from os import <env accessor>")


def scan_env_reads(source: str, rel_path: str) -> list[Hit]:
    if rel_path in _EXEMPT_FILES:
        return []
    scanner = _EnvScanner(rel_path)
    scanner.visit(ast.parse(source))
    return scanner.hits


def test_env_is_read_only_in_core_config() -> None:
    hits = []
    for rel, tree in source_files():
        if rel in _EXEMPT_FILES:
            continue
        scanner = _EnvScanner(rel)
        scanner.visit(tree)
        hits.extend(scanner.hits)
    assert hits == [], f"environment reads outside core/config.py: {hits}"


def test_exempt_file_really_reads_the_environment() -> None:
    reads = []
    for rel, tree in source_files():
        if rel in _EXEMPT_FILES:
            scanner = _EnvScanner(rel)
            scanner.visit(tree)
            reads.extend(scanner.hits)
    assert reads, "core/config.py no longer reads the environment: drop it from _EXEMPT_FILES"


def test_allowlist_is_empty() -> None:
    assert _ALLOWLIST == frozenset()


def test_guard_flags_planted_violations() -> None:
    planted = "import os\nfrom os import getenv\na = os.environ['X']\nb = os.getenv('Y')\n"
    assert [h.detail for h in scan_env_reads(planted, "services/x.py")] == [
        "from os import <env accessor>",
        "os.environ",
        "os.getenv",
    ]


def test_exempt_file_is_not_scanned() -> None:
    assert scan_env_reads("import os\nos.environ\n", "core/config.py") == []
