"""Drift check (CLAUDE.md §6): the OCR document reader's route and error codes are defined only
in ``shared_library.data_contracts``; no service source re-types them as string literals."""

from __future__ import annotations

import ast
from pathlib import Path

from shared_library.data_contracts import OCR_DOCUMENTS_ROUTE, OcrDocumentErrorCode

_SERVICES = Path(__file__).resolve().parents[2]
_SSOT_FILE = _SERVICES / "common" / "src" / "shared_library" / "data_contracts.py"
# Error codes are matched exactly (voice's own outward code "ocr_document_not_found" is a different
# contract); the route prefix is matched as a substring so f-string path pieces are caught too.
_CODES = [c.value for c in OcrDocumentErrorCode]
_ROUTE_PREFIX = OCR_DOCUMENTS_ROUTE.split("{")[0].rstrip("/")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                ids.add(id(first.value))
    return ids


def _string_literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = _docstring_nodes(tree)
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_services_tree_is_where_the_scan_expects():
    assert _SERVICES.is_dir(), _SERVICES
    for sub in ("ocr/src", "octo_agent/src", "voice/src"):
        assert (_SERVICES / sub).is_dir(), f"missing {_SERVICES / sub}"


def test_no_service_retypes_the_reader_route_or_error_codes():
    offenders = []
    for path in sorted(_SERVICES.glob("*/src/**/*.py")):
        if path == _SSOT_FILE:
            continue
        for lineno, value in _string_literals(path):
            if value in _CODES or _ROUTE_PREFIX in value:
                offenders.append(f"{path.relative_to(_SERVICES)}:{lineno} {value!r}")
    assert not offenders, (
        "re-typed reader contract literals (use shared_library.data_contracts):\n"
        + "\n".join(offenders)
    )
