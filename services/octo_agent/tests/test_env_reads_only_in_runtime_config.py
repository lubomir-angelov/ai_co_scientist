"""Fitness test (CLAUDE.md §6): ``RuntimeConfig.from_env()`` is the only environment reader
in ``services/octo_agent/src``. Every other module goes through it, so this is one enforced
source of truth for environment configuration rather than N hand-maintained copies.

An AST scan, not a grep: it looks for the actual ``os.environ`` / ``os.getenv`` access shapes
regardless of formatting, and is immune to the string "environ" appearing in a comment or a
docstring.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[1] / "src"

# The one file allowed to read the environment directly — every other module must go
# through RuntimeConfig.from_env().
_EXEMPT_FILES = frozenset({"runtime_config.py"})

# Reviewed, deliberate exceptions: (path relative to src/, the string-constant naming the
# environment variable). Each entry is a code-review event, never a blanket exemption. This
# one is the tool's own reviewed __main__ demo/manual-check input.
_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {("tools/document_parser_ocr/tool.py", "OCR_SAMPLE_INPUT")}
)


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _first_string_arg(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def _is_environ_reference(node: ast.expr) -> bool:
    """``os.environ`` (module-qualified) or a bare ``environ`` name (post `from os import`)."""
    if isinstance(node, ast.Attribute):
        return node.attr == "environ" and isinstance(node.value, ast.Name) and node.value.id == "os"
    return isinstance(node, ast.Name) and node.id == "environ"


def _is_getenv_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr == "getenv" and isinstance(func.value, ast.Name) and func.value.id == "os"
    return isinstance(func, ast.Name) and func.id == "getenv"


def _find_violations(rel_path: str, tree: ast.AST) -> list[str]:
    violations: list[str] = []
    parents = _build_parent_map(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name in ("environ", "getenv"):
                    violations.append(f"{rel_path}:{node.lineno}: 'from os import {alias.name}'")
            continue

        if isinstance(node, ast.Call) and _is_getenv_call(node):
            var_name = _first_string_arg(node)
            if (rel_path, var_name) not in _ALLOWLIST:
                violations.append(f"{rel_path}:{node.lineno}: environment read of {var_name!r}")
            continue

        if not _is_environ_reference(node):
            continue

        # `os.environ` (or bare `environ`) itself. Allowed only as the base of a `.get(...)`
        # call naming an allowlisted variable — `os.environ["X"]`, a bare reference passed
        # around, or `.get(...)` with a non-allowlisted/non-literal name are all violations.
        parent = parents.get(id(node))
        if isinstance(parent, ast.Attribute) and parent.attr == "get" and parent.value is node:
            call = parents.get(id(parent))
            if isinstance(call, ast.Call) and call.func is parent:
                var_name = _first_string_arg(call)
                if (rel_path, var_name) in _ALLOWLIST:
                    continue
                violations.append(f"{rel_path}:{node.lineno}: environment read of {var_name!r}")
                continue
        violations.append(f"{rel_path}:{node.lineno}: 'environ' access outside .get(...)")

    return violations


def test_no_environment_reads_outside_runtime_config() -> None:
    violations: list[str] = []
    for path in sorted(_SRC_DIR.rglob("*.py")):
        if path.name in _EXEMPT_FILES:
            continue
        rel_path = path.relative_to(_SRC_DIR).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        violations.extend(_find_violations(rel_path, tree))

    assert violations == [], (
        "Environment variables must be read only through RuntimeConfig.from_env() "
        "(CLAUDE.md §6). Violations:\n" + "\n".join(violations)
    )
