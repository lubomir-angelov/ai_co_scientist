from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    graph_backend: str = "falkordb"  # or "neo4j", "kuzu", "neptune"
    falkor_host: str = "localhost"
    falkor_port: int = 6379

    # LLM / embeddings – Graphiti expects OpenAI-compatible provider
    openai_api_key: str
    openai_base_url: str | None = None

    class Config:
        env_prefix = "MEMORY_"

settings = Settings()
