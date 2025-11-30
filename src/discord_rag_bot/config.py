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
    llm_system_prompt: str | None = None
    # Bot branding / guilds
    bot_status: str | None = "OneLiteFeather RAG"
    guild_ids: list[int] = []  # optional, for guild-specific command sync
    enable_message_content_intent: bool = False  # required for mention/reply triggers in guilds
    # RAG behavior
    rag_fallback_to_llm: bool = True
    rag_mix_llm_with_rag: bool = False
    rag_mix_threshold: float | None = None
    rag_score_kind: str = "similarity"  # 'similarity' or 'distance'
    # Ingestion defaults
    ingest_exts: list[str] = [
        ".md",
        ".py",
        ".yml",
        ".yaml",
        ".toml",
        ".json",
        ".txt",
    ]
    # Queue watch polling interval (seconds)
    queue_watch_poll_sec: float = 5.0
    # ETL staging directory (for manifests)
    etl_staging_dir: str = ".staging"
    etl_staging_backend: str = "local"  # local|s3
    # S3 staging (optional, used when etl_staging_backend=s3)
    s3_staging_bucket: Optional[str] = None
    s3_staging_prefix: str = "rag-artifacts"
    s3_region: Optional[str] = None
    s3_endpoint_url: Optional[str] = None  # e.g., http://minio:9000
    s3_access_key_id: Optional[str] = None
    s3_secret_access_key: Optional[str] = None
    # Job backend selection: postgres (default) | redis | rabbitmq
    job_backend: str = "postgres"
    # Redis configuration (optional; used when job_backend=redis)
    redis_url: Optional[str] = None  # e.g., redis://localhost:6379/0
    redis_namespace: str = "rag"
    # RabbitMQ configuration (optional; used when job_backend=rabbitmq)
    rabbitmq_url: Optional[str] = None  # e.g., amqp://user:pass@localhost:5672/
    rabbitmq_queue: str = "rag_jobs"
    # RAG gating / mode
    rag_mode: str = "auto"  # auto|rag|llm
    rag_gate_strategy: str = "llm"  # llm|heuristic|hybrid
    rag_min_question_len: int = 12
    rag_keywords: list[str] = [
        "onelitefeather",
        "plugin",
        "java",
        "stacktrace",
        "error",
        "yaml",
        "config.yml",
        "plugin.yml",
        ".yml",
        ".java",
        "github",
        "release",
        "build",
        "gradle",
        "maven",
        "api",
        "javadoc",
    ]
    # Gating threshold (optional). If set and RAG mode is auto, use RAG only when score passes this threshold.
    rag_gate_threshold: float | None = None
    # Smalltalk detection (configurable)
    smalltalk_exact: list[str] = [
        "hi",
        "hallo",
        "hey",
        "moin",
        "servus",
        "danke",
        "thx",
        "ok",
        "yo",
        "lol",
        "danke!",
        "merci",
        "bitte",
        "gern",
        "gerne",
    ]
    smalltalk_contains: list[str] = [
        "guten morgen",
        "guten abend",
        "gute nacht",
        "wie geht",
        "wie läuft",
        "alles gut",
        "was geht",
        "na?",
        "moin moin",
        "grüß",
        "danke dir",
        "vielen dank",
        # Selbstbezug/Identität
        "wer bist du",
        "was bist du",
        "wo bist du",
        "wie heißt du",
        "wie heisst du",
        "dein name",
        "was kannst du",
        "kannst du mir helfen",
        "hilf mir",
        "hilfe",
        "help",
        "test bot",
        "nur ein test",
        "test?",
        "ping",
    ]
    # Ollama specific
    ollama_base_url: Optional[str] = None  # e.g. http://localhost:11434
    # vLLM (OpenAI-compatible) specific
    vllm_base_url: Optional[str] = None  # e.g. http://localhost:8000/v1
    vllm_api_key: Optional[str] = None
    table_name: str = "rag_chunks"
    embed_dim: int = 1536
    top_k: int = 6

    # Estimation parameters (for /estimate commands)
    estimate_tokens_per_sec: float = 2500.0  # approximate embedding throughput
    estimate_db_writes_per_sec: float = 200.0  # approximate upsert rate
    estimate_overhead_sec: float = 5.0  # fixed overhead per job
    # Health HTTP server (for k8s probes)
    health_http_port: Optional[int] = None  # e.g., 8080 to enable /healthz

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
