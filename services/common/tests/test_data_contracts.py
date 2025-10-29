from datetime import datetime
from shared_library import (
    OCRRequest,
    OCRResponse,
    OCRSection,
    OCRTable,
    FactTriple,
    UpsertFactsRequest,
)

def test_ocr_models_roundtrip():
    req = OCRRequest(doc_id="paper-123", content_b64="ZmFrZV9iYXNlNjQ=")
    assert req.doc_id == "paper-123"

    resp = OCRResponse(
        doc_id="paper-123",
        sections=[OCRSection(name="Abstract", text="We propose...")],
        tables=[OCRTable(caption="Results", rows=[{"temp_C": 450, "yield_MPa": 512}])],
        metadata={"title": "Cool Photonics Paper"},
    )
    assert resp.sections[0].name == "Abstract"

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
