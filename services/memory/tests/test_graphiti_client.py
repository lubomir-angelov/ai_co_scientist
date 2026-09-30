from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from graphiti_core.driver.falkordb.fulltext import build_falkor_fulltext_query

from memory_service import graphiti_client
from memory_service.config import Settings
from memory_service.graphiti_client import LocalFalkorDriver


class RecordingFalkorDriver(LocalFalkorDriver):
    """The real FalkorDB client connects in its constructor; only record the arguments."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        super().__init__(falkor_db=MagicMock(), database=kwargs["database"])


def test_build_graphiti_uses_only_local_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graphiti_client, "LocalFalkorDriver", RecordingFalkorDriver)
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


def _local_driver() -> LocalFalkorDriver:
    """A LocalFalkorDriver with no live FalkorDB connection (query building only)."""
    return LocalFalkorDriver(falkor_db=MagicMock(), database="photonic_memory")


def test_build_fulltext_query_drops_bare_underscore_token() -> None:
    # Reproduces the traceback: LaTeX ``\mathbb{T}_{ij}`` sanitizes to a lone "_" token
    # (the surrounding "{"/"}" become whitespace, "_" is not in FalkorDB's separator map),
    # which previously crashed RediSearch with "Syntax error ... near T".
    query = (
        r"global network structure realized via circuit operation \mathbb{T}_{ij} and "
        r"\mathrm{M} illustrated in Fig. 3c"
    )

    result = _local_driver().build_fulltext_query(query)

    assert " _ " not in f" {result} "
    assert not result.endswith("| _")
    assert not result.startswith("_ |")
    # Real tokens on either side of the dropped "_" survive.
    assert "mathbb" in result
    assert "mathrm" in result
    assert "T" in result.split()


def test_build_fulltext_query_underscore_only_input_is_empty() -> None:
    assert _local_driver().build_fulltext_query("_") == ""
    assert _local_driver().build_fulltext_query("_ __ ___") == ""


def test_build_fulltext_query_matches_graphiti_builder_for_normal_input() -> None:
    query = "silicon photonics waveguide coupling"

    assert _local_driver().build_fulltext_query(query) == build_falkor_fulltext_query(query)


def test_build_fulltext_query_preserves_group_filter_when_dropping_tokens() -> None:
    result = _local_driver().build_fulltext_query("network _ structure", group_ids=["papers"])

    assert result.startswith('(@group_id:"papers")')
    assert "_" not in result.split(") (", 1)[1]
