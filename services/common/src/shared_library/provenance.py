from datetime import datetime, timezone
from typing import Any, Dict

def build_fact(
    *,
    subject: str,
    predicate: str,
    obj: str,
    conditions: Dict[str, Any],
    source_doc: str,
    evidence_span: str,
    valid_at: datetime | None = None,
) -> dict:
    """
    Helper to create a dict shaped like FactTriple for UpsertFactsRequest.
    Ensures required provenance fields are always present.
    """
    if valid_at is None:
        valid_at = datetime.now(timezone.utc)

    return {
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "conditions": conditions,
        "valid_at": valid_at,
        "source_doc": source_doc,
        "evidence_span": evidence_span,
    }
