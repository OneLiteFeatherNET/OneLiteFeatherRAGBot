# src/discord_rag_bot/config.py
from typing import Optional
from pydantic_settings import BaseSettings
from rag_core import Db

class Settings(BaseSettings):
    # Common
    discord_token: Optional[str] = None
    # AI provider selection: openai (default) or ollama
    ai_provider: str = "openai"
    llm_model: str = "gpt-4.1-mini"
    embed_model: str = "text-embedding-3-small"
    temperature: float = 0.1
    embed_provider: str = "openai"  # openai|ollama
    # Bot branding / guilds
    bot_status: str | None = "OneLiteFeather RAG"
    guild_ids: list[int] = []  # optional, for guild-specific command sync
    enable_message_content_intent: bool = False  # required for mention/reply triggers in guilds
    # Ollama specific
    ollama_base_url: Optional[str] = None  # e.g. http://localhost:11434
    # vLLM (OpenAI-compatible) specific
    vllm_base_url: Optional[str] = None  # e.g. http://localhost:8000/v1
    vllm_api_key: Optional[str] = None
    table_name: str = "rag_chunks"
    embed_dim: int = 1536
    top_k: int = 6

    # Database (required for RAG API service or direct DB usage)
    pg_host: Optional[str] = None
    pg_port: int = 5432
    pg_user: Optional[str] = None
    pg_password: Optional[str] = None
    pg_database: Optional[str] = None

    @property
    def db(self) -> Db:
        if not all([self.pg_host, self.pg_user, self.pg_password, self.pg_database]):
            raise ValueError("Postgres settings missing: set APP_PG_HOST, APP_PG_USER, APP_PG_PASSWORD, APP_PG_DATABASE")
        return Db(
            host=self.pg_host,  # type: ignore[arg-type]
            port=self.pg_port,
            user=self.pg_user,  # type: ignore[arg-type]
            password=self.pg_password,  # type: ignore[arg-type]
            database=self.pg_database,  # type: ignore[arg-type]
        )

    class Config:
        env_prefix = "APP_"
        extra = "ignore"

settings = Settings()
