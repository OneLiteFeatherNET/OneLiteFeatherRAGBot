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
    # Admin roles allowed to use admin commands (IDs or names)
    admin_role_ids: list[int] = []
    admin_role_names: list[str] = []
    # Config backend for prompts/settings: db (default) or file
    config_backend: str = "db"
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
    job_queue_default: str = "rag_jobs"
    job_queue_ingest: str | None = None
    job_queue_checksum: str | None = None
    job_queue_prune: str | None = None
    # RabbitMQ configuration (optional; used when job_backend=rabbitmq)
    rabbitmq_url: Optional[str] = None  # e.g., amqp://user:pass@localhost:5672/
    rabbitmq_queue: str = "rag_jobs"
    # RAG gating / mode
    rag_mode: str = "auto"  # auto|rag|llm
    rag_gate_strategy: str = "llm"  # llm|heuristic|hybrid
    rag_min_question_len: int = 12
    # Gating threshold (optional). If set and RAG mode is auto, use RAG only when score passes this threshold.
    rag_gate_threshold: float | None = None
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

    # UI/messages (make user-facing text configurable)
    reply_placeholder_text: Optional[str] = None  # e.g., "🧠 Einen kleinen Moment …"
    chat_style_append: Optional[str] = None  # extra style instructions appended to the system prompt
    language_hint_template: Optional[str] = None  # e.g., "Antwortsprache: {lang}"
    sources_heading: Optional[str] = None  # e.g., "Sources:" or "Quellen:"
    reply_context_label: Optional[str] = None  # e.g., "Context (previous bot message):"
    credits_exhausted_message: Optional[str] = None  # message when no credits available
    memory_summary_heading: Optional[str] = None
    memory_recent_heading: Optional[str] = None
    memory_user_prefix: Optional[str] = None
    memory_bot_prefix: Optional[str] = None

    # Credits & Budgeting
    credit_enabled: bool = False
    credit_period: str = "month"  # month|rolling
    credit_global_cap: int = 100000  # total credits per period across all users
    credit_default_limit: int = 1000  # per-user default credits per period
    # JSON maps, e.g.: {"gold": 5000, "silver": 2000}
    credit_rank_limits: dict[str, int] = {}
    # Map role name -> rank (JSON), e.g.: {"Gold": "gold", "VIP": "gold"}
    credit_role_ranks_by_name: dict[str, str] = {}
    # Map role ID (as string) -> rank (JSON), e.g.: {"123456": "gold"}
    credit_role_ranks_by_id: dict[str, str] = {}
    # Roles with unlimited per-user credit (still respects global cap)
    credit_unlimited_role_names: list[str] = []
    credit_unlimited_role_ids: list[int] = []
    # Estimation: ~tokens per char and expected output tokens; 1 credit per 1k tokens by default
    credit_tokens_per_char: float = 0.25
    credit_est_output_tokens: int = 600
    credit_per_1k_tokens: float = 1.0

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
