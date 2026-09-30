"""Construction of a fully local Graphiti instance (FalkorDB + local LLM + local embeddings)."""

from __future__ import annotations

import logging
import os

# Graphiti sends anonymous usage telemetry unless disabled. This service must not make
# hidden network calls, so default it off before graphiti_core is imported.
os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")

from graphiti_core import Graphiti  # noqa: E402
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient  # noqa: E402
from graphiti_core.driver.falkordb.fulltext import (  # noqa: E402
    build_falkor_fulltext_query,
    sanitize_falkor_fulltext_query,
)
from graphiti_core.driver.falkordb_driver import FalkorDriver  # noqa: E402
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig  # noqa: E402
from graphiti_core.llm_client.config import LLMConfig  # noqa: E402
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402

from .config import Settings  # noqa: E402

logger = logging.getLogger(__name__)


class LocalFalkorDriver(FalkorDriver):
    """FalkorDriver that drops bare non-alphanumeric tokens before building fulltext queries.

    graphiti-core 0.30.2's ``sanitize_falkor_fulltext_query`` replaces FalkorDB's special
    characters with whitespace, but a token left with *no* letter or digit (e.g. a lone
    ``_`` surviving where ``\\mathbb{T}_{ij}``-style LaTeX split on ``{``/``}``) passes
    through untouched. RediSearch's query parser then raises a syntax error on that bare
    token, and there is no upstream fix in the latest release. This override filters those
    tokens out and delegates the rest (group-id escaping, stopword filtering, the
    query-length cap) to Graphiti's own ``build_falkor_fulltext_query``, which stays the
    single source of truth for that logic.
    """

    def build_fulltext_query(
        self, query: str, group_ids: list[str] | None = None, max_query_length: int = 128
    ) -> str:
        alphanumeric_tokens = [
            token
            for token in sanitize_falkor_fulltext_query(query).split()
            if any(character.isalnum() for character in token)
        ]
        return build_falkor_fulltext_query(
            ' '.join(alphanumeric_tokens), group_ids, max_query_length
        )


def build_graphiti(settings: Settings) -> Graphiti:
    """
    Build a Graphiti instance wired only to local services.

    Every client is passed explicitly: Graphiti's defaults would otherwise create
    OpenAI cloud clients that require OPENAI_API_KEY.
    """
    driver = LocalFalkorDriver(
        host=settings.falkordb_host,
        port=settings.falkordb_port,
        username=settings.falkordb_username,
        password=(
            settings.falkordb_password.get_secret_value() if settings.falkordb_password else None
        ),
        database=settings.graph_name,
    )

    llm_config = LLMConfig(
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        small_model=settings.llm_small_model or settings.llm_model,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    llm_http = AsyncOpenAI(
        api_key=llm_config.api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )
    llm_client = OpenAIGenericClient(
        config=llm_config,
        client=llm_http,
        max_tokens=settings.llm_max_tokens,
        structured_output_mode=settings.llm_structured_output,
    )

    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
            api_key=settings.embedding_api_key.get_secret_value(),
            base_url=settings.embedding_base_url,
        ),
        client=AsyncOpenAI(
            api_key=settings.embedding_api_key.get_secret_value(),
            base_url=settings.embedding_base_url,
            timeout=settings.embedding_timeout_seconds,
            max_retries=2,
        ),
    )

    # Only used by cross-encoder search recipes; the backend uses RRF search, but the
    # client must still point at the local LLM rather than Graphiti's cloud default.
    cross_encoder = OpenAIRerankerClient(config=llm_config, client=llm_http)

    logger.info(
        "Graphiti configured: falkordb=%s:%s graph=%s llm_model=%s embedding_model=%s",
        settings.falkordb_host,
        settings.falkordb_port,
        settings.graph_name,
        settings.llm_model,
        settings.embedding_model,
    )
    return Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
        max_coroutines=settings.graphiti_max_coroutines,
    )
