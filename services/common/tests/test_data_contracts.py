import pytest

from datetime import datetime
from pydantic import TypeAdapter, ValidationError
from shared_library.data_contracts import (
    OCR_FULLTEXT_SECTION,
    DocId,
    OCRBlock,
    OCRPage,
    OCRRequest,
    OCRResponse,
    OCRSection,
    OCRTable,
    OcrDocumentError,
    OcrDocumentErrorCode,
    FactTriple,
    UpsertFactsRequest,
    ocr_document_path,
    ocr_page_section_name,
)


def test_ocr_models_roundtrip():
    req = OCRRequest(doc_id="paper-123", content_b64="ZmFrZV9iYXNlNjQ=")
    assert req.doc_id == "paper-123"

    resp = OCRResponse(
        doc_id="paper-123",
        sections=[OCRSection(name="Abstract", text="We propose...")],
        tables=[OCRTable(caption="Results", rows=[{"temp_C": 450, "yield_MPa": 512}])],
        pages=[
            OCRPage(
                page_number=1,
                blocks=[OCRBlock(ref="text", bbox=(1, 2, 3, 4), text="We propose...")],
            )
        ],
        metadata={"title": "Cool Photonics Paper", "page_count": 1},
    )
    assert resp.sections[0].name == "Abstract"
    assert resp.pages[0].blocks[0].text == "We propose..."
    assert OCRResponse.model_validate_json(resp.model_dump_json()) == resp


def _response(pages: list[OCRPage], metadata: dict) -> OCRResponse:
    return OCRResponse(
        doc_id="d", sections=[], tables=[], pages=pages, metadata=metadata
    )


def test_ocr_response_requires_contiguous_pages():
    with pytest.raises(ValidationError, match="contiguous"):
        _response([OCRPage(page_number=2, blocks=[])], {"page_count": 1})


def test_ocr_response_requires_page_count_matching_pages():
    with pytest.raises(ValidationError, match="does not match"):
        _response([OCRPage(page_number=1, blocks=[])], {"page_count": 2})


def test_ocr_response_requires_page_count_metadata():
    with pytest.raises(ValidationError, match="page_count is required"):
        _response([], {})


def test_ocr_response_requires_pages_field():
    with pytest.raises(ValidationError):
        OCRResponse.model_validate(
            {"doc_id": "d", "sections": [], "tables": [], "metadata": {"page_count": 0}}
        )


@pytest.mark.parametrize("bad", ["", "a/b", "has space", "tab\there"])
def test_doc_id_rejects_illegal_ids(bad):
    with pytest.raises(ValidationError):
        TypeAdapter(DocId).validate_python(bad)
    with pytest.raises(ValidationError):
        OCRRequest(doc_id=bad, content_b64="x")


@pytest.mark.parametrize("good", ["paper-123", "arxiv:2410.12345", "file:my_paper"])
def test_doc_id_accepts_legal_ids(good):
    assert TypeAdapter(DocId).validate_python(good) == good


def test_fact_models():
    fact = FactTriple(
        subject="Alloy_X",
        predicate="has_yield_strength",
        object="512 MPa",
        conditions={"temperature_C": 450},
        valid_at=datetime.utcnow(),
        source_doc="doi:10.1234/foo",
        evidence_span="Results, paragraph 3",
    )
    upsert = UpsertFactsRequest(facts=[fact])
    assert upsert.facts[0].subject == "Alloy_X"


def test_ocr_page_section_name_is_the_one_shared_definition():
    assert OCR_FULLTEXT_SECTION == "FullText"
    assert ocr_page_section_name(1) == "Page 1"
    assert ocr_page_section_name(12) == "Page 12"
    with pytest.raises(ValueError):
        ocr_page_section_name(0)


def test_ocr_document_path_percent_encodes_the_doc_id():
    assert ocr_document_path("a b") == "/ocr/documents/a%20b"
    assert ocr_document_path("p:1") == "/ocr/documents/p%3A1"


def test_ocr_document_error_roundtrips_and_rejects_unknown_code():
    body = OcrDocumentError(
        code=OcrDocumentErrorCode.NOT_FOUND, doc_id="d1"
    ).model_dump(mode="json")
    assert body == {"code": "document_not_found", "doc_id": "d1"}
    assert OcrDocumentError.model_validate(body).code is OcrDocumentErrorCode.NOT_FOUND
    with pytest.raises(ValidationError):
        OcrDocumentError.model_validate({"code": "something_else", "doc_id": "d1"})
