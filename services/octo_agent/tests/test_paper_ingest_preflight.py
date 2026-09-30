from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from paper_ingest import preflight


def _response(status: int, body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body
    resp.text = str(body)
    return resp


def test_connection_refused_counts_as_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight.requests, "get", MagicMock(side_effect=requests.ConnectionError()))
    preflight.require_down("LLM gateway", "http://llm:9000/v1/models", "llm-down")  # does not raise


def test_any_http_response_raises_gpu_tenant_error_with_make_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preflight.requests, "get", MagicMock(return_value=_response(401, {})))
    with pytest.raises(preflight.GpuTenantError, match="make llm-down"):
        preflight.require_down("LLM gateway", "http://llm:9000/v1/models", "llm-down")


def test_timeout_raises_gpu_tenant_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight.requests, "get", MagicMock(side_effect=requests.Timeout()))
    with pytest.raises(preflight.GpuTenantError, match="ocr-down"):
        preflight.require_down("OCR", "http://ocr:8002/healthz", "ocr-down")


def test_wait_llm_serving_fails_when_model_not_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    get = MagicMock(return_value=_response(200, {"data": [{"id": "other-model"}]}))
    monkeypatch.setattr(preflight.requests, "get", get)

    with pytest.raises(preflight.ServiceNotReadyError, match="other-model"):
        preflight.wait_llm_serving(
            "http://llm:9000/v1", "key", "wanted-model", 0.0, sleep=lambda s: None
        )


def test_wait_llm_serving_succeeds_when_model_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    get = MagicMock(return_value=_response(200, {"data": [{"id": "wanted-model"}]}))
    monkeypatch.setattr(preflight.requests, "get", get)

    preflight.wait_llm_serving("http://llm:9000/v1", "key", "wanted-model", 10, sleep=lambda s: None)


def test_waiting_times_out_with_last_observed_state(monkeypatch: pytest.MonkeyPatch) -> None:
    get = MagicMock(return_value=_response(200, {"ready": False}))
    monkeypatch.setattr(preflight.requests, "get", get)

    fake_clock = iter([0.0, 3.0, 6.0, 11.0])
    sleeps: list[float] = []

    with pytest.raises(preflight.ServiceNotReadyError, match="ready.*False"):
        preflight.wait_memory_ready(
            "http://memory:8005", 10, sleep=sleeps.append, now=lambda: next(fake_clock)
        )
    assert sleeps  # it polled at least once before giving up
