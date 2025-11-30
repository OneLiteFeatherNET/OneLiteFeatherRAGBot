OneLiteFeather Discord RAG Bot (pgvector + LlamaIndex)
======================================================

Overview
- Discord bot + queue-based worker ecosystem that talks directly to Postgres/pgvector for retrieval-based answers (no REST intermediary).
- Conversation memory: per-user Kontext + kompakte Zusammenfassung wird in Postgres gespeichert und fließt in Antworten ein.
- Queue jobs are delivered via RabbitMQ with Postgres metadata so multiple workers can scale horizontally; an indexing CLI is still available for ad-hoc runs.
- Modular architecture: commands/listeners, DI services, provider abstraction (OpenAI, Ollama, vLLM) and built-in Prometheus metrics for Discord, RAG, and jobs.
- docker-compose includes Postgres/pgvector and optional Ollama for local end-to-end testing.
  - vLLM support via OpenAI-compatible provider (set `APP_AI_PROVIDER=vllm`).

Services
- `bot`: Discord client with direct pgvector access, Postgres-stored prompts, optional health/metrics server, and role-based admin permissions (`APP_ADMIN_ROLE_*`).
- `worker`: `rag-run-queue` consuming RabbitMQ jobs while Postgres keeps progress/status/history for `/queue list/show` and metrics.
Scaling is now queue-type-aware: start multiple `rag-run-queue` workers with `--queue-type ingest|checksum|prune` (or set `APP_WORKER_QUEUE_TYPE` per deployment) so each worker binds to the RabbitMQ queue defined by that job type (`APP_JOB_QUEUE_<TYPE>`).

- Optional `ollama` container for local LLM/embeddings (port 11434) when `APP_AI_PROVIDER=ollama`.

Scaling
- Deploying to Kubernetes: use the provided bot and worker deployments plus the dedicated HPAs (`k8s/bot-hpa.yaml`, `k8s/worker-hpa.yaml`).
- The bot exposes `/metrics`, `/healthz`, `/readyz` on `APP_HEALTH_HTTP_PORT` so k8s liveness/readiness and Prometheus scraping work.
- Workers will auto-scale through RabbitMQ and the `rag-run-queue` HPA; configure RabbitMQ + Postgres as a shared queue reference.
- Style: Antworten sind hilfreich mit trockenem Sarkasmus und passenden Discord‑Emojis; Emoji-/Style‑Guides können via RAG indexiert werden.



Code Structure
- `src/discord_rag_bot/` – application layer for the bot
  - `app.py` – entrypoint (`discord-rag-bot` script)
  - `bot/` – bot client, DI services, startup wiring
  - `commands/` – modular slash command cogs (auto‑loaded)
  - `listeners/` – message listeners (e.g., mention/reply chat) auto‑loaded separately
  - `infrastructure/` – adapters/factories (e.g., AI provider factory)
  - `util/` – small helpers (e.g., text clipping)
- `src/rag_core/` – core RAG domain and provider abstraction
  - `rag_service.py` – vector store, index, query/index API
  - `providers/` – `OpenAIProvider`, `OllamaProvider` implementing `AIProvider`
  - `types.py` – shared dataclasses (e.g., `Db`)
  - `ingestion/` – pluggable sources (filesystem, GitHub repo/org) with checksum skipping
- `src/rag_cli/` – CLI for indexing (`rag-index`)
  - supports `--config` YAML with multiple sources
  - example schema:
    ```yaml
    sources:
      - type: local_dir
        path: /data/repos/my-repo
        repo_url: https://github.com/ORG/my-repo
        exts: [".md", ".py"]
      - type: github_repo
        repo: https://github.com/ORG/another-repo
        branch: main
        exts: [".md", ".py"]
      - type: github_org
        org: my-org
        visibility: public   # all|public|private (token required for private)
        include_archived: false
        topics: []
        exts: [".md", ".py"]
        branch: main
        token: ${GITHUB_TOKEN}
      - type: web_url
        urls:
          - https://docs.oracle.com/javase/8/docs/api/
          - https://javadoc.io/doc/org.springframework/spring-core/latest/index.html
      - type: sitemap
        sitemap_url: https://example.com/sitemap.xml
        limit: 200
      - type: website
        start_urls: ["https://example.com/docs/"]
        allowed_prefixes: ["https://example.com/docs/"]
        max_pages: 500
    ```
- `src/rag_core/ingestion/` – pluggable ingestion sources
  - `base.py` – `IngestionSource` interface
  - `filesystem.py` – local directory source
  - `github.py` – GitHub repo/org sources (clone via git, list via API)
  - `composite.py` – combine multiple sources
  - `chunked.py` – chunking wrapper for per‑chunk checksums
  - `../chunking.py` – paragraph‑aware chunker utility
  - `web.py` – URL, sitemap, and website crawler sources (useful for JavaDocs and docs websites)
  

Environment (APP_ prefix)
- Bot: `APP_DISCORD_TOKEN`
- Bot UX: `APP_BOT_STATUS` (presence), optional `APP_GUILD_IDS` (JSON array for guild-scoped sync)
- DB: `APP_PG_HOST`, `APP_PG_PORT`, `APP_PG_USER`, `APP_PG_PASSWORD`, `APP_PG_DATABASE`
- RAG: `APP_TABLE_NAME`, `APP_EMBED_DIM`, `APP_TOP_K`
- Provider selection: `APP_AI_PROVIDER` (`openai`|`ollama`|`vllm`), `APP_LLM_MODEL`, `APP_EMBED_MODEL`, `APP_TEMPERATURE`, optional `APP_OLLAMA_BASE_URL`
- OpenAI: `OPENAI_API_KEY` (when using `openai` provider)
- vLLM: `APP_VLLM_BASE_URL`, optional `APP_VLLM_API_KEY`; choose embeddings via `APP_EMBED_PROVIDER` (`openai` | `ollama` | `vllm`). When `APP_EMBED_PROVIDER=vllm`, embeddings are requested via the vLLM OpenAI‑compatible `/embeddings` endpoint.
 - Logging: `APP_LOG_LEVEL` (DEBUG/INFO/...) for bot/CLI/worker
- RAG behavior: driven by an LLM gating strategy (`APP_RAG_GATE_STRATEGY=llm`). The LLM reads the context and decides whether to use retrieval or respond plainly.
- Hybrid/threshold mode: `APP_RAG_GATE_THRESHOLD` can still enforce retrieval when scores meet your configured threshold (useful for auto|hybrid modes).
- The bot automatically detects the user language (via langdetect) and instructs the LLM to respond in that language, so answers never randomly switch tongues.


Quickstart (Docker Compose)
1. Copy `.env.example` to `.env` and set required values.
2. Start: `docker compose up --build`
3. Index repositories/content (choose one):
   - Host: `uv run rag-index /path/to/repo https://github.com/ORG/repo`
   - Docker: `docker compose run --rm bot rag-index /data/repos/my-repo https://github.com/ORG/my-repo`
   - Config: `uv run rag-index --config ingest.yaml`
   - Enable chunking: add `--chunk-size 2000 --chunk-overlap 200` or set in YAML (`chunk_size`, `chunk_overlap`)
   - Queue runner: `uv run rag-run-queue --once` (single job) or `uv run rag-run-queue` (daemon loop)
4. Use `/ask <question>` in Discord. The bot queries pgvector directly.

Checksum‑based reindexing
- The indexer stores per‑document checksums in a small Postgres table (`rag_checksums`).
- On re‑index, unchanged documents are skipped automatically.
- Document identity uses a stable `doc_id` (e.g., `<repo_url>@<relative_path>` for filesystem/Git repos).

Local Development (no Docker)
- Install dependencies, set env variables, then:
  - Bot: `uv run discord-rag-bot`
  - Indexing: `uv run rag-index /path/to/repo https://github.com/ORG/repo`
  - Multi-source indexing: `uv run rag-index --config ingest.yaml`

Ollama (optional)
- Compose starts `ollama` on port 11434.
- Set `.env`: `APP_AI_PROVIDER=ollama`, `APP_LLM_MODEL=<e.g., llama3.1>`, `APP_EMBED_MODEL=<e.g., nomic-embed-text>`, `APP_OLLAMA_BASE_URL=http://ollama:11434`.
- Ensure `APP_EMBED_DIM` matches the embedding model (e.g., 768 for `nomic-embed-text`).

vLLM (optional)
- Run a vLLM server exposing an OpenAI‑compatible API.
- Set `.env`: `APP_AI_PROVIDER=vllm`, `APP_VLLM_BASE_URL=http://localhost:8000/v1`, `APP_LLM_MODEL=<served model>`.
- Choose embeddings via `APP_EMBED_PROVIDER` (`openai` or `ollama`) and set the corresponding embedding model/config.

Extending the Bot
- Add a new file under `src/discord_rag_bot/commands/<name>.py` with a Cog and an `async def setup(bot)` function that adds the Cog.
- Cogs can access shared services via `bot.services` (e.g., `bot.services.rag`).

Message-based Q&A (mention/reply)
- You can trigger RAG answers by mentioning the bot or replying to the bot and writing a question.
- Enable in `.env`: `APP_ENABLE_MESSAGE_CONTENT_INTENT=true` and enable the “Message Content Intent” in the Discord Developer Portal for your bot.
 - When replying to the bot, any text you add is treated as your question and the replied bot message is included as context automatically.
 - Prefix commands are disabled intentionally; only slash commands and mentions/replies are supported.

Memory commands
- `/memory show [scope: channel|all] [user] [limit] [ephemeral]` – zeigt gespeichertes Gedächtnis (Zusammenfassung + letzte Schritte). Ohne `user` wird dein eigenes angezeigt. Andere Nutzer nur für Admins.
- `/memory clear [scope: channel|all] [user] [confirm] [ephemeral]` – löscht Gedächtnis. Ohne `user` löscht du dein eigenes. Andere Nutzer nur für Admins. `confirm:true` erforderlich.

Credits (Admin)
- `/credits stats` – zeigt globale Nutzung und Cap (aktueller Monat)
- `/credits show [user]` – zeigt Nutzung eines Nutzers
- `/credits set-user-limit user:<user> limit:<n>` – setzt benutzerbezogenes Limit (überschreibt Rangregeln)
- `/credits clear-user-limit user:<user>` – entfernt benutzerbezogenes Limit
- `/credits add-unlimited-role role:<role>` – Rolle erhält unendliche Credits (globaler Cap gilt weiterhin)
- `/credits remove-unlimited-role role:<role>` – entfernt unendliche Rolle
- `/credits list-unlimited-roles` – listet unendliche Rollen

License
MIT — see `LICENSE`.
  - `run_queue.py` – queue worker (`rag-run-queue`) that processes jobs created from Discord

Index queue from Discord
- `/queue github repo repo:<url> [branch] [exts] [chunk_size] [chunk_overlap]`
- `/queue github org org:<name> [visibility] [include_archived] [topics] [branch] [exts] [chunk_size] [chunk_overlap]`
- `/queue local dir repo_root:<path> repo_url:<url> [exts] [chunk_size] [chunk_overlap]`
- `/queue list [status] [limit]` – list jobs (admin only)
- `/queue show job_id:<id>` – show job details (admin only)
- `/queue retry job_id:<id>` – retry failed/canceled job (admin only)
- `/queue cancel job_id:<id>` – cancel pending/processing job (best‑effort, admin only)
- Then run the worker: `uv run rag-run-queue --once` or as a long‑running process.

Checksum-only updates
- You can queue checksum refresh jobs without re-indexing vectors:
  - `/queue checksum github_repo repo:<url> [branch] [exts]`
  - `/queue checksum local_dir repo_root:<path> repo_url:<url> [exts]`
  - `/queue checksum web_url urls:"https://a.com, https://b.com"`
  - `/queue checksum website start_url:<url> [allowed_prefixes] [max_pages]`
  - The bot builds an ETL manifest first and enqueues a `checksum_update` job. The worker loads the manifest and updates checksums only.
