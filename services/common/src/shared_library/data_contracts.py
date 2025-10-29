from pydantic import BaseModel

# ocr
class OCRRequest(BaseModel):
    doc_id: str
    content_b64: str  # PDF or image bytes, base64

class OCRSection(BaseModel):
    name: str
    text: str

class OCRTable(BaseModel):
    caption: str
    rows: list[dict]

class OCRResponse(BaseModel):
    doc_id: str
    sections: list[OCRSection]
    tables: list[OCRTable]
    metadata: dict


# memory
class FactTriple(BaseModel):
    subject: str
    predicate: str
    object: str
    conditions: dict
    valid_at: datetime
    source_doc: str
    evidence_span: str

class UpsertFactsRequest(BaseModel):
    facts: list[FactTriple]
