# memory_service/config.py

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # FalkorDB / Graphiti
    graphiti_uri: str = "falkor://falkordb:6379"
    graph_name: str = "photonic_memory"
    llm_provider: str = "openai"
    embedding_provider: str = "openai"

    # If Graphiti needs direct OpenAI config, you can pass via env
    openai_api_key: str | None = None
    openai_base_url: str | None = None

    class Config:
        env_prefix = "MEMORY_"


settings = Settings()
