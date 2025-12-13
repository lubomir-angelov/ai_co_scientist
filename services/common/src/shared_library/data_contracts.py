from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field
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
    """
    Minimal metadata about a paper the co-scientist reads.
    """
    paper_id: str = Field(
        description="Stable identifier, e.g. 'arxiv:2410.12345' or a DOI."
    )
    title: str
    authors: List[str] = Field(default_factory=list)
    venue: Optional[str] = None
    year: Optional[int] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = Field(
        default=None,
        description="Publication date; used as valid_at for initial facts if present.",
    )


class PaperSectionEpisodeIn(BaseModel):
    """
    A chunk of a paper section (e.g. Abstract, Intro), used when ingesting PDFs.
    """
    paper: PaperMeta
    section_name: str
    section_index: int = Field(
        description="Sequential index of the section within the paper."
    )
    chunk_index: int = Field(
        description="Sequential index of this chunk within the section."
    )
    text: str = Field(
        description="Raw text of this chunk (post OCR / parsing / cleaning)."
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="When this chunk was ingested. Defaults to 'now' if not provided.",
    )


class PaperNoteEpisodeIn(BaseModel):
    """
    A user-authored note/question/idea attached to some location in a paper.
    """
    paper: PaperMeta
    location_hint: Optional[str] = Field(
        default=None,
        description="Optional location pointer, e.g. 'Fig. 2', 'Eq. (3)', 'Sec. 3.1'.",
    )
    note_text: str
    note_type: str = Field(
        default="question",
        description="Tag: 'question' | 'idea' | 'critique' | 'summary' | ...",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="When the note was created. Defaults to 'now' if not provided.",
    )


class ConceptQuery(BaseModel):
    """
    High-level query for 'what do we know about X in the literature?'.
    """
    query_text: str = Field(
        description="Natural-language topic, e.g. 'microring resonator thermal tuning'."
    )
    time_filter_as_of: Optional[datetime] = Field(
        default=None,
        description=(
            "If set, retrieve facts as of this time (temporal 'as-of' query). "
            "If None, use current time."
        ),
    )
    limit: int = Field(
        default=30,
        ge=1,
        le=200,
        description="Maximum number of facts to return.",
    )


class MemoryFact(BaseModel):
    """
    A single retrieved fact from the temporal knowledge graph.
    """
    fact: str = Field(
        description="Natural-language fact / claim / summary from the graph."
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="When this fact edge was created in the graph.",
    )
    valid_at: Optional[datetime] = Field(
        default=None,
        description="When this fact became true in-world (publication / discovery time).",
    )
    invalid_at: Optional[datetime] = Field(
        default=None,
        description=(
            "If set, the time at which this fact was superseded or invalidated. "
            "If null, the fact is currently considered valid."
        ),
    )
    expired_at: Optional[datetime] = Field(
        default=None,
        description="Optional expiry time for transient beliefs.",
    )
    episodes: List[str] = Field(
        default_factory=list,
        description="List of episode IDs that support / generated this fact.",
    )
    source_node_uuid: Optional[str] = Field(
        default=None,
        description="Backend node UUID for the subject of the fact (if exposed).",
    )
    target_node_uuid: Optional[str] = Field(
        default=None,
        description="Backend node UUID for the object of the fact (if exposed).",
    )
