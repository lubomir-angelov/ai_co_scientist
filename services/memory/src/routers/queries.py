from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from ..graphiti_client import get_graphiti

router = APIRouter(tags=["queries"])

class EntityFilters(BaseModel):
    hypothesis_ids: Optional[List[str]] = None
    entity_types: Optional[List[str]] = None

class TimeFilter(BaseModel):
    kind: str = "none"   # "none" | "as_of" | "between"
    as_of: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None

class MemoryQuery(BaseModel):
    project_id: str
    mode: str
    natural_query: Optional[str] = None
    entity_filters: Optional[EntityFilters] = None
    time_filter: Optional[TimeFilter] = None
    limit: int = 20

class Fact(BaseModel):
    subject: Dict[str, Any]
    predicate: str
    object: Dict[str, Any]
    fact_text: str
    valid_at: str
    invalid_at: Optional[str]
    provenance: Dict[str, Any]
    confidence: float
    score: float
    evidence: List[str]

class QueryResponse(BaseModel):
    facts: List[Fact]


@router.post("/query", response_model=QueryResponse)
async def query_memory(q: MemoryQuery):
    graphiti = get_graphiti()

    # PSEUDO-CODE: hybrid search
    #
    # 1. Use graphiti's semantic/keyword search for edges related to q.natural_query
    # 2. Filter by project_id, entity types, and time window using graph constraints
    # 3. Re-rank / score as needed
    #
    # For example (not exact API):
    #
    # edges = await graphiti.search_edges(
    #     query=q.natural_query or "",
    #     filters={...},
    #     limit=q.limit,
    # )

    edges = []  # replace with real query

    facts: List[Fact] = []
    for e in edges:
        facts.append(
            Fact(
                subject={"id": e.subject_id, "type": e.subject_type},
                predicate=e.predicate,
                object={"id": e.object_id, "type": e.object_type},
                fact_text=e.fact_text,
                valid_at=e.valid_at,
                invalid_at=e.invalid_at,
                provenance=e.provenance,
                confidence=e.confidence,
                score=e.score,
                evidence=e.evidence,
            )
        )

    return QueryResponse(facts=facts)
