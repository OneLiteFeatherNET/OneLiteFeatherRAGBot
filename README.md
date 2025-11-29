Discord RAG Bot (pgvector + LlamaIndex)
=======================================

Overview
- Primary interface is a Discord bot that queries a Postgres/pgvector store directly — no REST layer.
- Ingestion/Indexing is triggered via a Python CLI (one‑off or scheduled via cron).
- Layered, maintainable architecture with a dedicated commands package and a provider abstraction (OpenAI or Ollama).
- docker‑compose provided for local testing with Postgres/pgvector (and optional Ollama).

Services
- bot: Discord bot with direct access to pgvector.
- optional: `ollama` service for local LLM/embeddings (port 11434). Only needed when `APP_AI_PROVIDER=ollama`.

Code Structure
- `src/discord_rag_bot/` – application layer for the bot
  - `app.py` – entrypoint (`discord-rag-bot` script)
  - `bot/` – bot client, DI services, startup wiring
  - `commands/` – modular command cogs (auto‑loaded)
  - `infrastructure/` – adapters/factories (e.g., AI provider factory)
  - `util/` – small helpers (e.g., text clipping)
- `src/rag_core/` – core RAG domain and provider abstraction
  - `rag_service.py` – vector store, index, query/index API
  - `providers/` – `OpenAIProvider`, `OllamaProvider` implementing `AIProvider`
  - `types.py` – shared dataclasses (e.g., `Db`)
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
    ```
- `src/rag_core/ingestion/` – pluggable ingestion sources
  - `base.py` – `IngestionSource` interface
  - `filesystem.py` – local directory source
  - `github.py` – GitHub repo/org sources (clone via git, list via API)
  - `composite.py` – combine multiple sources
  

Environment (APP_ prefix)
- Bot: `APP_DISCORD_TOKEN`
- DB: `APP_PG_HOST`, `APP_PG_PORT`, `APP_PG_USER`, `APP_PG_PASSWORD`, `APP_PG_DATABASE`
- RAG: `APP_TABLE_NAME`, `APP_EMBED_DIM`, `APP_TOP_K`
- Provider selection: `APP_AI_PROVIDER` (`openai`|`ollama`), `APP_LLM_MODEL`, `APP_EMBED_MODEL`, `APP_TEMPERATURE`, optional `APP_OLLAMA_BASE_URL`
- OpenAI: `OPENAI_API_KEY` (when using `openai` provider)

Quickstart (Docker Compose)
1. Copy `.env.example` to `.env` and set required values.
2. Start: `docker compose up --build`
3. Index repositories/content (choose one):
   - Host: `uv run rag-index /path/to/repo https://github.com/ORG/repo`
   - Docker: `docker compose run --rm bot rag-index /data/repos/my-repo https://github.com/ORG/my-repo`
   - Config: `uv run rag-index --config ingest.yaml`
4. Use `/ask <question>` in Discord. The bot queries pgvector directly.

Local Development (no Docker)
- Install dependencies, set env variables, then:
  - Bot: `uv run discord-rag-bot`
  - Indexing: `uv run rag-index /path/to/repo https://github.com/ORG/repo`
  - Multi-source indexing: `uv run rag-index --config ingest.yaml`

Ollama (optional)
- Compose starts `ollama` on port 11434.
- Set `.env`: `APP_AI_PROVIDER=ollama`, `APP_LLM_MODEL=<e.g., llama3.1>`, `APP_EMBED_MODEL=<e.g., nomic-embed-text>`, `APP_OLLAMA_BASE_URL=http://ollama:11434`.
- Ensure `APP_EMBED_DIM` matches the embedding model (e.g., 768 for `nomic-embed-text`).

Extending the Bot
- Add a new file under `src/discord_rag_bot/commands/<name>.py` with a Cog and an `async def setup(bot)` function that adds the Cog.
- Cogs can access shared services via `bot.services` (e.g., `bot.services.rag`).

License
MIT — see `LICENSE`.
