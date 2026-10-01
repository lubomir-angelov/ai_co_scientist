"""
Make the OCR server importable without the GPU stack.

server.py imports torch, transformers and pdf2image at module level. Unit tests
never load the model (the lifespan is not run), so lightweight stand-ins are
installed for any of those packages that are missing. Inside the OCR image the
real packages are used.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
# server.py uses "from utils import ...", so src/ must be importable too.
sys.path[:0] = [str(SERVICE_DIR), str(SERVICE_DIR / "src")]

# server.py builds its document store at import and requires this directory.
os.environ["OCR_DOCUMENTS_DIR"] = tempfile.mkdtemp(prefix="ocr_documents_test_")

_STUBS = {
    "torch": {"bfloat16": object()},
    "transformers": {"AutoModel": object, "AutoTokenizer": object},
    "pdf2image": {"convert_from_path": lambda *a, **k: []},
}

for name, attrs in _STUBS.items():
    if importlib.util.find_spec(name) is None:
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        sys.modules[name] = module
