import ast
import os
import threading
from pathlib import Path

import pytest
from shared_library.data_contracts import OCRBlock, OCRPage, OCRResponse, OCRSection

from document_store import (
    DocumentIntegrityError,
    DocumentNotFoundError,
    OcrDocumentReader,
    OcrDocumentWriter,
    document_path,
    documents_dir_from_env,
)


def _resp(doc_id: str = "doc-1", text: str = "hello") -> OCRResponse:
    return OCRResponse(
        doc_id=doc_id,
        sections=[OCRSection(name="Page 1", text=text)],
        tables=[],
        pages=[
            OCRPage(page_number=1, blocks=[OCRBlock(ref="text", bbox=None, text=text)])
        ],
        metadata={"page_count": 1},
    )


def test_roundtrip(tmp_path: Path) -> None:
    OcrDocumentWriter(tmp_path).save(_resp())
    assert OcrDocumentReader(tmp_path).load("doc-1") == _resp()


def test_save_is_atomic_and_replaces(tmp_path: Path) -> None:
    writer = OcrDocumentWriter(tmp_path)
    writer.save(_resp(text="one"))
    writer.save(_resp(text="two"))
    assert OcrDocumentReader(tmp_path).load("doc-1").pages[0].blocks[0].text == "two"
    assert [p.name for p in tmp_path.iterdir()] == [
        document_path(tmp_path, "doc-1").name
    ]


def test_load_missing_raises_not_found(tmp_path: Path) -> None:
    with pytest.raises(DocumentNotFoundError):
        OcrDocumentReader(tmp_path).load("nope")


def test_doc_id_mismatch_raises_integrity(tmp_path: Path) -> None:
    document_path(tmp_path, "wanted").write_text(
        _resp("other").model_dump_json(), encoding="utf-8"
    )
    with pytest.raises(DocumentIntegrityError, match="has doc_id 'other'"):
        OcrDocumentReader(tmp_path).load("wanted")


def test_legacy_document_without_pages_raises_integrity(tmp_path: Path) -> None:
    document_path(tmp_path, "old").write_text(
        '{"doc_id":"old","sections":[],"tables":[],"metadata":{"page_count":0}}',
        encoding="utf-8",
    )
    with pytest.raises(DocumentIntegrityError, match="OCRResponse contract"):
        OcrDocumentReader(tmp_path).load("old")


@pytest.mark.parametrize("cls", [OcrDocumentReader, OcrDocumentWriter])
def test_missing_root_raises(tmp_path: Path, cls: type) -> None:
    with pytest.raises(RuntimeError, match="does not exist"):
        cls(tmp_path / "absent")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permission bits")
def test_reader_accepts_read_only_root_that_writer_rejects(tmp_path: Path) -> None:
    OcrDocumentWriter(tmp_path).save(_resp())
    tmp_path.chmod(0o555)
    try:
        with pytest.raises(RuntimeError, match="not writable"):
            OcrDocumentWriter(tmp_path)
        assert OcrDocumentReader(tmp_path).load("doc-1") == _resp()
    finally:
        tmp_path.chmod(0o755)


def test_documents_dir_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OCR_DOCUMENTS_DIR", str(tmp_path))
    assert documents_dir_from_env() == tmp_path
    monkeypatch.setenv("OCR_DOCUMENTS_DIR", "")
    with pytest.raises(RuntimeError, match="OCR_DOCUMENTS_DIR must be set"):
        documents_dir_from_env()
    monkeypatch.delenv("OCR_DOCUMENTS_DIR")
    with pytest.raises(RuntimeError, match="OCR_DOCUMENTS_DIR must be set"):
        documents_dir_from_env()


def test_concurrent_saves_of_one_doc_id_never_corrupt(tmp_path: Path) -> None:
    writer = OcrDocumentWriter(tmp_path)
    start = threading.Barrier(2, timeout=5)
    errors: list[BaseException] = []

    def save(text: str) -> None:
        try:
            start.wait()
            writer.save(_resp(text=text))
        except BaseException as exc:  # surfaced by the assertion below, never swallowed
            errors.append(exc)

    threads = [threading.Thread(target=save, args=(t,)) for t in ("one", "two")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert OcrDocumentReader(tmp_path).load("doc-1").pages[0].blocks[0].text in {
        "one",
        "two",
    }
    assert [p.name for p in tmp_path.iterdir()] == [
        document_path(tmp_path, "doc-1").name
    ]


def test_src_never_calls_os_replace_directly() -> None:
    """Drift guard (CLAUDE.md §6): atomic writes go through shared_library.atomic_files only."""
    for path in sorted((Path(__file__).resolve().parents[1] / "src").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"replace", "rename"} or not (
                    isinstance(node.func.value, ast.Name) and node.func.value.id == "os"
                ), f"{path}:{node.lineno} calls os.{node.func.attr}"
