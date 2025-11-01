# services/ocr/tests/test_ocr_runtime.py
from src import ocr_runtime


def test_load_deepseek_ocr_returns_pipeline():
    pipe = ocr_runtime.load_deepseek_ocr()
    assert pipe is not None
    assert hasattr(pipe, "process_bytes")


def test_process_bytes_returns_expected_shape():
    pipe = ocr_runtime.load_deepseek_ocr()
    fake_bytes = b"fake-image"
    out = pipe.process_bytes(fake_bytes, doc_id="doc-1")
    assert "sections" in out
    assert "tables" in out
    assert "metadata" in out
    assert out["metadata"]["doc_id"] == "doc-1"
