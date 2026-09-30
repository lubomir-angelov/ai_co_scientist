"""
Memory Graph Tool:
 - Thin HTTP client for the memory service (Graphiti temporal knowledge graph).

Retrieval (for the planner):
  search   -> POST {base_url}/v1/memory/concepts/search
  changes  -> POST {base_url}/v1/memory/facts/changes
Logging sink (for the executor):
  record_step       -> POST {base_url}/v1/memory/agent/steps
  record_hypothesis -> POST {base_url}/v1/memory/hypotheses
Whole-paper ingest (for the paper-ingestion batch):
  ingest_paper      -> POST {base_url}/v1/memory/paper/ingest

Requests are validated with the shared_library contracts before they are sent, and responses
are validated against their contract before being returned.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from pydantic import BaseModel, TypeAdapter, ValidationError
from shared_library.data_contracts import (
    AgentStepEpisodeIn,
    ConceptQuery,
    EpisodeAck,
    FactChanges,
    FactChangesQuery,
    HypothesisEpisodeIn,
    MemoryFact,
    PaperIngestRequest,
    PaperIngestResponse,
)

from runtime_config import RuntimeConfig
from service_errors import MemoryServiceError
from tools.base import BaseTool

logger = logging.getLogger(__name__)

_ACTIONS: dict[str, tuple[str, type[BaseModel], TypeAdapter]] = {
    "search": ("/v1/memory/concepts/search", ConceptQuery, TypeAdapter(list[MemoryFact])),
    "changes": ("/v1/memory/facts/changes", FactChangesQuery, TypeAdapter(FactChanges)),
    "record_step": ("/v1/memory/agent/steps", AgentStepEpisodeIn, TypeAdapter(EpisodeAck)),
    "record_hypothesis": (
        "/v1/memory/hypotheses",
        HypothesisEpisodeIn,
        TypeAdapter(EpisodeAck),
    ),
    "ingest_paper": (
        "/v1/memory/paper/ingest",
        PaperIngestRequest,
        TypeAdapter(PaperIngestResponse),
    ),
}


class Memory_Graph_Tool(BaseTool):
    """
    OctoTools tool for the co-scientist's long-term temporal memory.
    """

    require_llm_engine = False

    def __init__(self) -> None:
        super().__init__(
            tool_name="Memory_Graph_Tool",
            tool_description=(
                "Long-term temporal memory over papers read, user notes, agent steps and "
                "hypotheses. 'search' returns facts about a topic (optionally as of a date); "
                "'changes' returns facts added or invalidated in a time window; "
                "'record_step' and 'record_hypothesis' write results back to memory; "
                "'ingest_paper' -> POST /v1/memory/paper/ingest writes a whole OCR-parsed "
                "paper as one episode per section chunk."
            ),
            tool_version="1.0.0",
            input_types={
                "action": (
                    "str - One of 'search', 'changes', 'record_step', 'record_hypothesis', "
                    "'ingest_paper'."
                ),
                "query_text": "str - Topic for 'search'/'changes', e.g. 'microring thermal tuning'.",
                "time_filter_as_of": "str - ISO datetime; 'search' facts valid at that time.",
                "include_invalidated": "bool - 'search' also returns superseded facts.",
                "since": "str - ISO datetime; start of the 'changes' window.",
                "until": "str - ISO datetime; end of the 'changes' window (default now).",
                "limit": "int - Maximum number of facts (default 30).",
                "run_id, step_index, sub_goal, tool_name, result_summary, succeeded": (
                    "Fields for 'record_step'."
                ),
                "hypothesis_id, version, statement, rationale, status, confidence": (
                    "Fields for 'record_hypothesis'."
                ),
                "paper": (
                    "dict - PaperMeta {paper_id, title, published_at?, year?, ...} for "
                    "'ingest_paper'."
                ),
                "sections": (
                    "list - [{name, text}] OCR sections for 'ingest_paper' (send page "
                    "sections, not FullText)."
                ),
                "timeout_s": (
                    "float - per-call timeout; default MEMORY_REQUEST_TIMEOUT_SECONDS. A "
                    "whole-paper ingest needs minutes per page."
                ),
            },
            output_type=(
                "dict - search: {facts:[{fact, valid_at, invalid_at, source_kinds, ...}]}; "
                "changes: {added:[...], invalidated:[...]}; "
                "record_*: {episode_id, created, nodes_extracted, facts_extracted}; "
                "ingest_paper: {paper_id, episodes:[{episode_id, created, nodes_extracted, "
                "facts_extracted}]}"
            ),
            demo_commands=[
                {
                    "command": (
                        "execution = tool.execute(action='search', "
                        "query_text='microring resonator Q factor')"
                    ),
                    "description": "Retrieve what is currently known about microring Q factors.",
                },
                {
                    "command": (
                        "execution = tool.execute(action='changes', "
                        "query_text='phase-change photonics', since='2024-01-01T00:00:00Z')"
                    ),
                    "description": "List facts about PCM photonics that changed since 2024.",
                },
                {
                    "command": (
                        "execution = tool.execute(action='ingest_paper', timeout_s=3600, "
                        "paper={'paper_id': 'arxiv:2410.12345', 'title': 'Example Paper'}, "
                        "sections=[{'name': 'Page 1', 'text': '...'}])"
                    ),
                    "description": "Ingest every page section of a paper as memory episodes.",
                },
            ],
            user_metadata={
                "source_kinds": (
                    "Each fact lists the kinds of episodes backing it: paper_section, "
                    "paper_note, agent_step, hypothesis. Only paper_section facts are "
                    "literature claims."
                ),
            },
        )
        env = RuntimeConfig.from_env()
        self.base_url = env.memory_base_url.rstrip("/")
        self.default_timeout_s = env.memory_request_timeout_seconds

    def execute(self, action: str, timeout_s: float | None = None, **params: Any) -> dict[str, Any]:
        if action not in _ACTIONS:
            raise ValueError(f"Unknown action {action!r}; expected one of {sorted(_ACTIONS)}")
        path, request_model, response_adapter = _ACTIONS[action]
        try:
            payload = request_model.model_validate(params).model_dump(mode="json")
        except ValidationError as exc:
            raise ValueError(f"Invalid parameters for memory action {action!r}: {exc}") from exc

        effective_timeout = float(timeout_s) if timeout_s is not None else self.default_timeout_s
        status_code, body = self._post(path, payload, effective_timeout)

        try:
            validated = response_adapter.validate_python(body)
        except ValidationError as exc:
            raise MemoryServiceError(
                f"Memory service response for {action!r} violates its contract: {exc}",
                status_code=status_code,
            ) from exc

        dumped = response_adapter.dump_python(validated, mode="json")
        return {"facts": dumped} if action == "search" else dumped

    def _post(self, path: str, payload: dict[str, Any], timeout_s: float) -> tuple[int, Any]:
        url = f"{self.base_url}{path}"
        logger.info("Memory request: POST %s", url)
        try:
            resp = requests.post(url, json=payload, timeout=timeout_s)
        except requests.RequestException as exc:
            logger.error("Memory service unreachable: POST %s: %s", url, exc)
            raise MemoryServiceError(
                f"Memory service unreachable at {url} (timeout={timeout_s}s): {exc}",
                status_code=None,
            ) from exc

        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text
            logger.error("Memory service error %s on POST %s: %s", resp.status_code, url, detail)
            raise MemoryServiceError(
                f"Memory service error {resp.status_code} on POST {url}: {detail}",
                status_code=resp.status_code,
            )
        try:
            return resp.status_code, resp.json()
        except ValueError as exc:
            raise MemoryServiceError(
                f"Memory service returned non-JSON body on POST {url}",
                status_code=resp.status_code,
            ) from exc


if __name__ == "__main__":
    # Manual check against a running memory service (MEMORY_BASE_URL, default localhost:8005):
    #   PYTHONPATH=src:../common/src python -m tools.memory_graph.tool
    import json

    tool = Memory_Graph_Tool()
    result = tool.execute(action="search", query_text="microring resonator", limit=5)
    print(json.dumps(result, indent=2, ensure_ascii=False))
