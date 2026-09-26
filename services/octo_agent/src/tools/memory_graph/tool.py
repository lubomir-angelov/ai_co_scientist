"""
Memory Graph Tool:
 - Thin HTTP client for the memory service (Graphiti temporal knowledge graph).

Retrieval (for the planner):
  search   -> POST {base_url}/v1/memory/concepts/search
  changes  -> POST {base_url}/v1/memory/facts/changes
Logging sink (for the executor):
  record_step       -> POST {base_url}/v1/memory/agent/steps
  record_hypothesis -> POST {base_url}/v1/memory/hypotheses

Requests are validated with the shared_library contracts before they are sent.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests
from pydantic import BaseModel, ValidationError
from shared_library.data_contracts import (
    AgentStepEpisodeIn,
    ConceptQuery,
    FactChangesQuery,
    HypothesisEpisodeIn,
)

from tools.base import BaseTool

logger = logging.getLogger(__name__)

_ACTIONS: dict[str, tuple[str, type[BaseModel]]] = {
    "search": ("/v1/memory/concepts/search", ConceptQuery),
    "changes": ("/v1/memory/facts/changes", FactChangesQuery),
    "record_step": ("/v1/memory/agent/steps", AgentStepEpisodeIn),
    "record_hypothesis": ("/v1/memory/hypotheses", HypothesisEpisodeIn),
}


class MemoryServiceError(RuntimeError):
    """The memory service returned an error or could not be reached."""


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
                "'record_step' and 'record_hypothesis' write results back to memory."
            ),
            tool_version="1.0.0",
            input_types={
                "action": "str - One of 'search', 'changes', 'record_step', 'record_hypothesis'.",
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
            },
            output_type=(
                "dict - search: {facts:[{fact, valid_at, invalid_at, source_kinds, ...}]}; "
                "changes: {added:[...], invalidated:[...]}; "
                "record_*: {episode_id, created, nodes_extracted, facts_extracted}"
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
            ],
            user_metadata={
                "source_kinds": (
                    "Each fact lists the kinds of episodes backing it: paper_section, "
                    "paper_note, agent_step, hypothesis. Only paper_section facts are "
                    "literature claims."
                ),
            },
        )
        self.base_url = os.environ.get("MEMORY_BASE_URL", "http://localhost:8005").rstrip("/")
        self.timeout_s = float(os.environ.get("MEMORY_REQUEST_TIMEOUT_SECONDS", "600"))

    def execute(self, action: str, **params: Any) -> dict[str, Any]:
        if action not in _ACTIONS:
            raise ValueError(f"Unknown action {action!r}; expected one of {sorted(_ACTIONS)}")
        path, request_model = _ACTIONS[action]
        try:
            payload = request_model.model_validate(params).model_dump(mode="json")
        except ValidationError as exc:
            raise ValueError(f"Invalid parameters for memory action {action!r}: {exc}") from exc

        body = self._post(path, payload)
        return {"facts": body} if action == "search" else body

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        logger.info("Memory request: POST %s", url)
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout_s)
        except requests.RequestException as exc:
            logger.error("Memory service unreachable: POST %s: %s", url, exc)
            raise MemoryServiceError(f"Memory service unreachable at {url}: {exc}") from exc

        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text[:500]
            logger.error("Memory service error %s on POST %s: %s", resp.status_code, url, detail)
            raise MemoryServiceError(f"Memory service error {resp.status_code}: {detail}")
        return resp.json()


if __name__ == "__main__":
    # Manual check against a running memory service (MEMORY_BASE_URL, default localhost:8005):
    #   PYTHONPATH=src:../common/src python -m tools.memory_graph.tool
    import json

    tool = Memory_Graph_Tool()
    result = tool.execute(action="search", query_text="microring resonator", limit=5)
    print(json.dumps(result, indent=2, ensure_ascii=False))
