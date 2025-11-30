OneLiteFeather Discord RAG Bot
==============================

Production‑ready Discord RAG bot using Postgres/pgvector + LlamaIndex with an autoscalable queue worker, conversation memory, admin tooling, and Helm packaging.

Features
- RAG over pgvector with provider abstraction (OpenAI, Ollama, vLLM)
- Conversation memory per user (recent context + auto‑maintained summary)
- Admin‑only LLM Tooling: index/re‑index GitHub repo/org, URLs, website, sitemap, local dir (GitHub org batched per repo)
- Response Policy: automatically choose thread vs. reply/channel, mention behavior, and placeholders
- Credits & Budgeting: per‑user limits by rank/roles, unlimited roles, global monthly cap, admin commands
- Kubernetes/Helm chart, HPAs and metrics/health endpoints
- Semantic Releases for app + Helm chart; images built/pushed to GHCR

Architecture
- bot: Discord client (slash commands + natural language), direct DB access, health/metrics server
- worker: queue consumer (`rag-run-queue`) for indexing/checksum/prune jobs
  - Queue‑type aware: run multiple workers with `--queue-type ingest|checksum|prune` (or `APP_WORKER_QUEUE_TYPE`)
- Metrics/health: `/metrics`, `/healthz`, `/readyz` on `APP_HEALTH_HTTP_PORT`, and `/version`

Code Structure
- `src/discord_rag_bot/` – application layer for the bot
  - `app.py` – entrypoint (`discord-rag-bot`)
  - `bot/` – bot client, DI services, startup wiring
  - `commands/` – slash command cogs (auto‑loaded)
  - `listeners/` – message listeners (mention/reply chat)
  - `infrastructure/` – adapters/factories (AI provider, config store, memory, credits, tools)
  - `util/` – helpers (text clipping)
- `src/rag_core/` – core RAG domain and provider abstraction
  - `rag_service.py` – vector store, index, query/index API
  - `providers/` – OpenAI/Ollama/vLLM providers
  - `ingestion/` – pluggable sources (filesystem, GitHub repo/org, web)
- `src/rag_cli/` – CLI for indexing (`rag-index`) + queue worker (`rag-run-queue`)

Configuration
- Use `.env` for local dev. See `.env.example` for a fully documented template (Discord/DB/Provider/RAG/ETL/UI/Credits/Policy).
- Critical variables:
  - Discord: `APP_DISCORD_TOKEN`, `APP_BOT_STATUS`, `APP_GUILD_IDS`, `APP_ENABLE_MESSAGE_CONTENT_INTENT`
  - Database: `APP_PG_HOST`, `APP_PG_PORT`, `APP_PG_USER`, `APP_PG_PASSWORD`, `APP_PG_DATABASE`
  - RAG store: `APP_TABLE_NAME`, `APP_EMBED_DIM`, `APP_TOP_K`
  - LlamaIndex docstore persistence: `APP_DOCSTORE_PERSIST`, `APP_DOCSTORE_DIR` (persists doc/index metadata to disk; vectors remain in Postgres pgvector)
  - Provider: `APP_AI_PROVIDER` (openai|ollama|vllm), `APP_LLM_MODEL`, `APP_EMBED_MODEL`, `APP_EMBED_PROVIDER`, `APP_TEMPERATURE`
  - Health: `APP_HEALTH_HTTP_PORT`
  - Queue/ETL: `APP_JOB_BACKEND` (postgres|rabbitmq), `APP_RABBITMQ_URL`, `APP_QUEUE_WATCH_POLL_SEC`, `APP_ETL_STAGING_BACKEND` (local|s3) + `APP_S3_*`
  - UI/messages & Response policy: placeholders, headings, thread/reply/mention (`APP_CHAT_STYLE_APPEND`, `APP_REPLY_PLACEHOLDER_TEXT`, `APP_SOURCES_HEADING`, `APP_POLICY_*`)
  - Credits: enable caps/limits (`APP_CREDIT_*`, rank mapping, unlimited roles)

Quickstart (Docker Compose)
1. Copy `.env.example` to `.env` and set required values.
2. Start: `docker compose up --build`
3. Index repositories/content (choose one):
   - Host: `uv run rag-index /path/to/repo https://github.com/ORG/repo`
   - Docker: `docker compose run --rm bot rag-index /data/repos/my-repo https://github.com/ORG/my-repo`
   - Config: `uv run rag-index --config ingest.yaml`
   - Enable chunking: add `--chunk-size 2000 --chunk-overlap 200` or set in YAML (`chunk_size`, `chunk_overlap`)
   - Queue runner: `uv run rag-run-queue --once` (single job) or `uv run rag-run-queue` (daemon loop)
4. Use `/ask <question>` in Discord.

Tip for Ollama
- If you see HTTP 500 from Ollama, choose a smaller model and ensure it is pulled:
  - `APP_LLM_MODEL=llama3.2:3b-instruct`, `APP_EMBED_MODEL=nomic-embed-text`, `APP_EMBED_DIM=768`
  - `ollama pull llama3.2:3b-instruct`, `ollama pull nomic-embed-text`

Message-based Q&A
- Mention the bot or reply to the bot and write your question.
- Enable in `.env`: `APP_ENABLE_MESSAGE_CONTENT_INTENT=true` and enable the “Message Content Intent” in the Discord Developer Portal.
- Response policy (threads/replies): The bot decides whether to open a thread for long/source‑heavy answers, reply in channel, and whether to mention you. Controlled via `APP_POLICY_*`.

Commands
- Memory
  - `/memory show [scope: channel|all] [user] [limit] [ephemeral]`
  - `/memory clear [scope: channel|all] [user] [confirm] [ephemeral]`
- Credits (Admin)
  - `/credits stats`, `/credits show [user]`
  - `/credits set-user-limit user:<user> limit:<n>`, `/credits clear-user-limit user:<user>`
  - `/credits add-unlimited-role role:<role>`, `/credits remove-unlimited-role role:<role>`, `/credits list-unlimited-roles`
- Queue
  - `/queue github repo repo:<url> [branch] [exts] [chunk_size] [chunk_overlap]`
  - `/queue github org org:<name> [visibility] [include_archived] [topics] [branch] [exts] [chunk_size] [chunk_overlap]`
  - `/queue local dir repo_root:<path> repo_url:<url> [exts] [chunk_size] [chunk_overlap]`
  - `/queue list|show|retry|cancel …`
  - Checksum‑only updates: `checksum github_repo|local_dir|web_url|website`
- Version
  - `/version` returns version, commit, build date (also `GET /version` on health port)

Natural‑language Tooling (Admin‑only)
- Just write what you want. Examples the planner understands (no JSON needed):
  - “Reindex https://github.com/ORG/REPO on main; only .md and .py; chunk 2000/200.”
  - “Crawl https://docs.example.com limited to that site. Max 150 pages.”
  - “Index this sitemap: https://example.com/sitemap.xml limit 500.”
  - “For org ORG, index public repos with topic ‘docs’, only .md.”
  - “Index my local repo at /data/repos/my-repo; public URL https://github.com/ORG/REPO.”
- Add “force” to ignore checksums: “Reindex … force.”
- The LLM auto‑planner triggers: GitHub repo/org (org → one job per repo), URLs, website, sitemap, local dir. Admin‑only by role/permissions.

Helm Chart
- Location: `charts/discord-rag-bot`
- Values highlights:
  - `image.repository/tag`, `bot.replicaCount`, `workers.types` (ingest/checksum/prune), `global.env/secretEnv`, `global.jobQueues`
  - Services/HPA: `bot.autoscaling`, `workers.autoscaling`
- Install example:
  - `helm install my-rag charts/discord-rag-bot \`
    `--set global.secretEnv.APP_DISCORD_TOKEN=… --set image.repository=ghcr.io/<owner>/discord-rag-bot`

CI/Release
- semantic-release creates GitHub releases/tags and bumps `pyproject.toml` + Helm `Chart.yaml` (Python bump script)
- Images built/pushed to GHCR (bot + worker) with build args embedded (version/commit/date)
- Chart published via chart-releaser on tags `v*`

License
MIT — see `LICENSE`.
