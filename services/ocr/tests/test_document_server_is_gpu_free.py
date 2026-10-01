"""Fitness guard: the ocr-documents reader must stay GPU-free (it runs while the LLM owns the GPU)."""

import ast
import os
import subprocess
import sys
from pathlib import Path

_FORBIDDEN = frozenset({"server", "torch", "transformers", "pdf2image", "ocr_runtime"})
_SRC = Path(__file__).resolve().parents[1] / "src" / "document_server.py"
# Import ``document_server`` with the GPU stack made unimportable (a None entry in sys.modules
# raises ImportError on import), so a transitive import of it fails here.
_BLOCKED_IMPORT = (
    "import sys\n"
    "for m in ('torch', 'transformers', 'pdf2image'):\n"
    "    sys.modules[m] = None\n"
    "import document_server\n"
)


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            parts = module.split(".")
            roots.add(parts[1] if parts[0] == "src" and len(parts) > 1 else parts[0])
            if module == "src" or node.level:
                roots.update(alias.name for alias in node.names)
    return roots


def test_document_server_imports_no_gpu_stack() -> None:
    offending = (
        _imported_roots(ast.parse(_SRC.read_text(encoding="utf-8"))) & _FORBIDDEN
    )
    assert not offending, (
        f"{_SRC.name} must stay GPU-free but imports {sorted(offending)}"
    )


def test_document_server_imports_with_gpu_stack_blocked(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "OCR_DOCUMENTS_DIR": str(tmp_path),
        "PYTHONPATH": os.pathsep.join(p for p in sys.path if p),
    }
    result = subprocess.run(
        [sys.executable, "-c", _BLOCKED_IMPORT],
        cwd=_SRC.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
