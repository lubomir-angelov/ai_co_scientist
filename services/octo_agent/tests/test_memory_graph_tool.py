from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from tools.memory_graph import tool as memory_tool
from tools.memory_graph.tool import Memory_Graph_Tool, MemoryServiceError


def _response(status: int, body) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body
    return resp


@pytest.fixture
def post(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setenv("MEMORY_BASE_URL", "http://memory:8005/")
    mock = MagicMock(return_value=_response(200, []))
    monkeypatch.setattr(memory_tool.requests, "post", mock)
    return mock


def test_search_posts_validated_query(post: MagicMock) -> None:
    post.return_value = _response(200, [{"fact": "Q = 1.2e6", "source_kinds": ["paper_section"]}])

    result = Memory_Graph_Tool().execute(
        action="search", query_text="microring", time_filter_as_of="2023-01-01T00:00:00Z"
    )

    assert result == {"facts": [{"fact": "Q = 1.2e6", "source_kinds": ["paper_section"]}]}
    url = post.call_args.args[0]
    payload = post.call_args.kwargs["json"]
    assert url == "http://memory:8005/v1/memory/concepts/search"
    assert payload["query_text"] == "microring"
    assert payload["limit"] == 30
    assert payload["include_invalidated"] is False
    assert payload["time_filter_as_of"].startswith("2023-01-01T00:00:00")
    assert post.call_args.kwargs["timeout"] > 0


def test_record_step_returns_ack(post: MagicMock) -> None:
    ack = {"episode_id": "ep-1", "created": True, "nodes_extracted": 2, "facts_extracted": 1}
    post.return_value = _response(200, ack)

    result = Memory_Graph_Tool().execute(
        action="record_step",
        run_id="run-1",
        step_index=0,
        sub_goal="parse paper",
        tool_name="Document_Parser_OCR_Tool",
        result_summary="3 sections",
    )

    assert result == ack
    assert post.call_args.args[0].endswith("/v1/memory/agent/steps")


def test_invalid_parameters_are_rejected_before_any_request(post: MagicMock) -> None:
    with pytest.raises(ValueError, match="record_hypothesis"):
        Memory_Graph_Tool().execute(action="record_hypothesis", hypothesis_id="H1", version=0)
    with pytest.raises(ValueError, match="Unknown action"):
        Memory_Graph_Tool().execute(action="delete_everything")
    post.assert_not_called()


def test_service_errors_are_raised_with_detail(post: MagicMock) -> None:
    post.return_value = _response(503, {"error": {"code": "backend_unavailable"}})
    with pytest.raises(MemoryServiceError, match="backend_unavailable"):
        Memory_Graph_Tool().execute(action="search", query_text="x")


def test_unreachable_service_raises(post: MagicMock) -> None:
    post.side_effect = requests.ConnectionError("refused")
    with pytest.raises(MemoryServiceError, match="unreachable"):
        Memory_Graph_Tool().execute(action="changes", query_text="x", since="2024-01-01")
