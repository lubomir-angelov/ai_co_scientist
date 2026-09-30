"""Runtime configuration for the memory service (environment variables, prefix ``MEMORY_``)."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEMORY_", extra="ignore")

    # --- FalkorDB (graph store) ---
    falkordb_host: str = "falkordb"
    falkordb_port: int = 6379
    falkordb_username: str | None = None
    falkordb_password: SecretStr | None = None
    graph_name: str = "photonic_memory"

    # --- LLM used by Graphiti for entity/fact extraction (OpenAI-compatible, local) ---
    llm_base_url: str = "http://llm-gateway:8000/v1"
    llm_api_key: SecretStr = SecretStr("local-llm")
    llm_model: str = Field(description="Model id served by the local LLM, e.g. the GGUF name.")
    llm_small_model: str | None = Field(
        default=None,
        description="Optional cheaper model for simple prompts; defaults to llm_model.",
    )
    llm_temperature: float = 0.6
    llm_max_tokens: int = 16384
    llm_structured_output: Literal["json_schema", "json_object"] = "json_schema"
    llm_timeout_seconds: float = 600.0

    # --- Embeddings (OpenAI-compatible /v1/embeddings, local) ---
    embedding_base_url: str = "http://embeddings:8080/v1"
    embedding_api_key: SecretStr = SecretStr("local-embeddings")
    embedding_model: str = "Qwen3-Embedding-0.6B"
    embedding_dim: int = 1024
    embedding_timeout_seconds: float = 60.0

    # --- Ingestion ---
    max_concurrent_episodes: int = Field(
        default=1,
        ge=1,
        description="Episodes processed concurrently. Graphiti recommends sequential ingestion.",
    )
    graphiti_max_coroutines: int = Field(
        default=4, ge=1, description="Concurrent LLM/embedding calls inside one episode."
    )
    chunk_max_chars: int = Field(default=4000, ge=200)

    # --- Startup ---
    init_retries: int = Field(default=10, ge=1)
    init_retry_delay_seconds: float = Field(default=3.0, ge=0.0)

    log_level: str = Field(
        default="INFO", validation_alias=AliasChoices("MEMORY_LOG_LEVEL", "LOG_LEVEL")
    )

    def summary(self) -> dict[str, object]:
        """Configuration summary safe to log (no secrets)."""
        return {
            "falkordb": f"{self.falkordb_host}:{self.falkordb_port}",
            "graph_name": self.graph_name,
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_structured_output": self.llm_structured_output,
            "embedding_base_url": self.embedding_base_url,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "max_concurrent_episodes": self.max_concurrent_episodes,
        }
