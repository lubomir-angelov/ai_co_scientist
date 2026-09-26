from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from graphiti_core.driver.falkordb_driver import FalkorDriver

from memory_service import graphiti_client
from memory_service.config import Settings


class RecordingFalkorDriver(FalkorDriver):
    """The real FalkorDB client connects in its constructor; only record the arguments."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        super().__init__(falkor_db=MagicMock(), database=kwargs["database"])


def test_build_graphiti_uses_only_local_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graphiti_client, "FalkorDriver", RecordingFalkorDriver)
    settings = Settings(
        llm_model="local-model",
        llm_base_url="http://llm-gateway:8000/v1",
        embedding_base_url="http://embeddings:8080/v1",
        embedding_dim=768,
        falkordb_password="db-secret",
    )

    graphiti = graphiti_client.build_graphiti(settings)

    assert os.environ["GRAPHITI_TELEMETRY_ENABLED"] == "false"
    assert graphiti.driver.kwargs == {
        "host": "falkordb",
        "port": 6379,
        "username": None,
        "password": "db-secret",
        "database": "photonic_memory",
    }
    assert str(graphiti.llm_client.client.base_url).startswith("http://llm-gateway:8000/v1")
    assert graphiti.llm_client.model == "local-model"
    assert graphiti.llm_client.structured_output_mode == "json_schema"
    assert str(graphiti.embedder.client.base_url).startswith("http://embeddings:8080/v1")
    assert graphiti.embedder.config.embedding_dim == 768
    assert str(graphiti.cross_encoder.client.base_url).startswith("http://llm-gateway:8000/v1")


def test_settings_summary_excludes_secrets() -> None:
    settings = Settings(llm_model="m", llm_api_key="super-secret", falkordb_password="pw")
    assert "super-secret" not in str(settings.summary())
    assert "pw" not in str(settings.summary().values())
