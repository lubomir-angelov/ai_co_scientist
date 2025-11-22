from datetime import datetime
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

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


# memory
class PaperMeta(BaseModel):
    paper_id: str              # "arxiv:2410.12345" or DOI
    title: str
    authors: List[str]
    venue: Optional[str] = None
    year: Optional[int] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = None


class PaperSectionEpisodeIn(BaseModel):
    paper: PaperMeta
    section_name: str          # "Abstract", "Introduction", "Results", ...
    section_index: int         # 0, 1, 2 for ordering
    text: str                  # raw section text
    chunk_index: int           # if you chunk sections
    created_at: Optional[datetime] = None


class PaperNoteEpisodeIn(BaseModel):
    paper: PaperMeta
    location_hint: Optional[str] = None  # "Fig.2", "Eq.(3)", "Sec.3.1"
    note_text: str
    note_type: str = "question"          # "question" | "idea" | "critique" | ...
    created_at: Optional[datetime] = None


class ConceptQuery(BaseModel):
    query_text: str             # "microring resonator thermal tuning"
    time_filter_as_of: Optional[datetime] = None
    limit: int = 30


class MemoryFact(BaseModel):
    fact: str
    created_at: Optional[datetime] = None
    valid_at: Optional[datetime] = None
    invalid_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    episodes: List[str] = []
    source_node_uuid: Optional[str] = None
    target_node_uuid: Optional[str] = None
