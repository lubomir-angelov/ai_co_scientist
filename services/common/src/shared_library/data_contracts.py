from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, model_validator
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
class EpisodeKind(str, Enum):
    """
    Origin of a memory episode. Used to keep paper claims, user input and
    agent-generated content distinguishable in the knowledge graph.
    """
    paper_section = "paper_section"
    paper_note = "paper_note"
    agent_step = "agent_step"
    hypothesis = "hypothesis"


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
    include_invalidated: bool = Field(
        default=False,
        description=(
            "If False (default), facts invalidated at or before the as-of time are "
            "excluded. If True, superseded facts are returned too (history view)."
        ),
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
    uuid: Optional[str] = Field(
        default=None,
        description="Backend identifier of the fact edge itself.",
    )
    relation: Optional[str] = Field(
        default=None,
        description="Relation name of the fact edge, e.g. 'REPORTS_RESULT'.",
    )
    source_kinds: List[EpisodeKind] = Field(
        default_factory=list,
        description=(
            "Kinds of the episodes backing this fact, so paper-derived claims stay "
            "distinguishable from user notes and agent hypotheses."
        ),
    )


class AgentStepEpisodeIn(BaseModel):
    """
    One executed step of an agent run (planner sub-goal -> tool call -> result).
    Written back by the orchestrator so later runs know what was tried.
    """
    run_id: str = Field(description="Identifier of the solver run.")
    step_index: int = Field(ge=0, description="Sequential step number within the run.")
    sub_goal: str = Field(description="What the planner wanted to achieve in this step.")
    tool_name: str = Field(description="Tool used for the step, e.g. 'Document_Parser_OCR_Tool'.")
    result_summary: str = Field(
        description="Short, factual summary of the tool result (not the raw output)."
    )
    succeeded: bool = Field(default=True, description="Whether the step achieved its sub-goal.")
    created_at: Optional[datetime] = Field(
        default=None,
        description="When the step ran. Defaults to 'now' if not provided.",
    )


class HypothesisEpisodeIn(BaseModel):
    """
    A versioned research hypothesis. Each new version is a new episode, so the
    graph can answer 'what changed between v1 and v2?'.
    """
    hypothesis_id: str = Field(description="Stable identifier across versions, e.g. 'H-ring-tuning'.")
    version: int = Field(ge=1, description="Monotonic version number of this hypothesis.")
    statement: str = Field(description="The hypothesis itself, stated as a claim.")
    rationale: Optional[str] = Field(
        default=None, description="Why the agent/user believes this, citing evidence where possible."
    )
    status: str = Field(
        default="proposed",
        description="Tag: 'proposed' | 'supported' | 'refuted' | 'superseded' | ...",
    )
    confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Subjective confidence in [0, 1]."
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="When this version was stated. Defaults to 'now' if not provided.",
    )


class PaperIngestRequest(BaseModel):
    """
    Ingest a whole OCR-parsed paper. Sections are chunked and written as
    individual episodes; re-sending the same paper skips chunks already stored,
    so an interrupted ingest can simply be retried.
    """
    paper: PaperMeta
    sections: List[OCRSection] = Field(min_length=1)


class EpisodeAck(BaseModel):
    """
    Result of writing one episode into memory.
    """
    episode_id: str = Field(description="Backend episode identifier.")
    created: bool = Field(
        description="False if an identical episode already existed and was not re-ingested."
    )
    nodes_extracted: int = Field(default=0, description="Entities extracted from the episode.")
    facts_extracted: int = Field(default=0, description="Fact edges extracted from the episode.")


class PaperIngestResponse(BaseModel):
    paper_id: str
    episodes: List[EpisodeAck]


def _as_utc(dt: datetime) -> datetime:
    """Naive datetimes are interpreted as UTC so they compare with aware ones."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class FactChangesQuery(BaseModel):
    """
    'What changed about X between two points in time?'
    """
    query_text: str = Field(description="Natural-language topic to scope the changes to.")
    since: datetime = Field(description="Start of the window (inclusive).")
    until: Optional[datetime] = Field(
        default=None, description="End of the window (inclusive). Defaults to now."
    )
    limit: int = Field(default=30, ge=1, le=200, description="Maximum facts per category.")

    @model_validator(mode="after")
    def _check_window(self) -> "FactChangesQuery":
        if self.until is not None and _as_utc(self.since) > _as_utc(self.until):
            raise ValueError("'since' must not be after 'until'")
        return self


class FactChanges(BaseModel):
    """
    Facts that became valid, and facts that were invalidated, within a window.
    """
    added: List[MemoryFact] = Field(default_factory=list)
    invalidated: List[MemoryFact] = Field(default_factory=list)
