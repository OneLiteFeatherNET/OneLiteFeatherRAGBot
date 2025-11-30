## [1.2.0](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/compare/v1.1.0...v1.2.0) (2025-11-30)

### Features

* **github:** add local-clone ingestion source and tool; add commit metadata toggle and GITHUB_TOKEN fallback to reduce rate limits ([3af35be](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/3af35beaeca871b97d446098a7097d1c1fed58f0))
* **queue:** prefer per-repo jobs for /queue github org (local clone per repo), add force support across web and local commands ([6497308](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/6497308d2172319c4f51eb075f162b6fea1df268))
* **tools:** planner advertises optional force:true in tool payloads for checksum-override reindex ([54c31e4](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/54c31e44fe6907fc951eadec7fda6e84f504f0a7))

### Bug Fixes

* **credits:** quote legacy reserved column name "limit" in SQL fallback to avoid Postgres syntax error ([1c2a326](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/1c2a326ed9570507f960050881d42a79702eea57))
* **policy:** add missing import for decide_response_policy in chat listener ([5b24ae2](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/5b24ae2f994136bd5845d069149c6314dfd9b6a3))

## [1.1.0](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/compare/v1.0.0...v1.1.0) (2025-11-30)

### Features

* **policy:** add response policy to decide thread/reply/mention and persist memory in thread; document env settings ([7ceec6e](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/7ceec6e2dfdf0db47725e444f22f0bb87b543938))
* **tools:** add LLM auto-planner to detect and trigger tools from natural language (admin-only, no JSON required from user) ([9c3a61e](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/9c3a61ea8283a871f5dfed49c54f4c841f6f2bc3))
* **tools:** add LLM-triggerable queue tools (web/github/local) with fenced JSON tool-calls and admin-only enforcement ([2d7580c](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/2d7580c437160bb6b2d49d1d443fe9f5a6d82a19))
* **version:** expose build version via /version slash command and /version HTTP endpoint; pass build args in Docker builds ([64b6169](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/64b6169a3501d4a81d26634a019c4385d546d54b))

### Bug Fixes

* **tools:** import QueueGithubOrgTool in startup to register tool ([5cd785b](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/5cd785bd7f887e94ee64416b741c684cd2862677))

## 1.0.0 (2025-11-30)

### Features

* **bot:** add '/health' admin command to report table dims, row count, provider and intent status ([3474bae](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/3474bae8e35c4428595fcda2fc48767a1a9f8256))
* **bot:** add OneLiteFeather-friendly UX options (presence text and guild-scoped command sync) ([8e18d2e](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/8e18d2e61330f1c402e4fdd9a99d47c8bccd493f))
* **bot:** add per-user conversation memory with summary and sarcastic emoji style in system prompt ([0a462e1](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/0a462e1617a56896ecb31dade1f2b7c51c494cc4))
* **bot:** brand as OneLiteFeather and enforce restrictive guild whitelist for slash commands; add script alias ([281eae4](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/281eae464618efa1e646c49d6691976c1218ad01))
* **bot:** support mention/reply message-based Q&A with optional Message Content Intent; document config ([84a97f9](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/84a97f93c740cb2765943ef488f5545842b7e44f))
* **chart:** add Helm chart for Discord bot and per-queue workers ([7ad16d5](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/7ad16d5e85293ee71dd56f754445c2af74ae6d62))
* **chat:** enhance user policy resolution by adding admin check and computing user limits ([3b2f3c0](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/3b2f3c0a12b606fb228bb55eb4878ed97a0d02a1))
* **chat:** include replied bot message as context; allow added reply text to extend the question ([0cbd22e](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/0cbd22e56ae9583c64534afb39ee088d2fe2241a))
* **checksum:** add '/queue checksum ...' subcommands to build manifests and enqueue checksum_update jobs; worker handles checksum_update via RAGService.update_checksums ([c531754](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/c531754c4ef26b2571568b7a3b7d805323c8fa7c))
* **cli:** add rag-index command for one-off or scheduled indexing ([6ff2ef4](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/6ff2ef440f4917ba7169ecdaf20ef0cd21806066))
* **commands:** add /memory show and /memory clear with admin protections and persistent backend support ([78b0200](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/78b02008d4ab8d76efdd6c4796e1e2a8e65d0439))
* **config:** add migration of .staging prompts into DB and admin command /config migrate_prompts_to_db ([8ac411d](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/8ac411d9e4600bf6aa6b1613eba859ce829f76b7))
* **config:** move system prompt storage to DB with fallback; add ensure and backend switch ([3458757](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/3458757e1759f48ebaf7ceaed80abffc0d464d1c))
* **config:** remove hardcoded prompts/messages; make chat style, placeholders, headings, and credit messages configurable via env/DB ([3fcb2bc](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/3fcb2bc0ef8806bee0514aa801ce828dc1fbcf6e))
* **core:** introduce provider abstraction (OpenAI/Ollama) and adapt RAGService to AIProvider; extend settings for provider selection ([ecaa8ee](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/ecaa8ee458b67a0d184c682a378a4247e3809a32))
* **credits:** add admin slash-commands to manage user limits and unlimited roles; enforce unlimited via roles/admin while respecting global cap ([72bdd26](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/72bdd263e63e0dee192075e3ea47748ab98e3659))
* **credits:** add per-user rank-based credit limits, global monthly cap, and pre-authorization to prevent overspend ([7d11856](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/7d118564a477179096417664a90dad53fc8e1430))
* **embeddings:** add vLLM embeddings support via OpenAI-compatible endpoint; update env and docs ([f0b849e](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/f0b849ee1aeeccdccab80206c098ab9df79bd1e7))
* **estimate:** add /estimate commands to predict indexing duration; add estimation tunables ([b65730b](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/b65730b715995c91d324cadf22820f8faccd83f5))
* **etl:** introduce generic ETL layer (artifact store + manifest) and queue-only indexing; prebuild manifests in queue commands and load in worker; prepare DB layer abstraction ([7ee44f5](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/7ee44f5fb6af15f1e31e4d880da6015c680c3068))
* **gating:** switch to LLM-based gating strategy with configurable env ([811cc9e](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/811cc9e98c008cbacfa06e1dbf0c4347a8484dce))
* **github,auth:** switch GitHub sources to PyGithub (repos, orgs, issues); add role-based admin permissions via env-configured role IDs/names ([584746e](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/584746eb5f3922dddfcb7ff5feec6ceabe978ebc))
* **indexing:** add checksum store and skip unchanged documents; introduce ingestion items with stable doc_id and checksums ([9fe1b45](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/9fe1b45a83d34f10cc8cfb73dc69ba1c2401a864))
* **indexing:** add immediate '/index github_repo|local_dir' admin commands; configurable default file extensions via APP_INGEST_EXTS; support force reindex; default exts applied to queue commands ([cb75ae3](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/cb75ae3dbc1c717dffa29e624524705b0065715c))
* **ingestion-web:** add URL/sitemap/website crawler sources; extend YAML config; add admin commands '/index web_url|website' and queue '/queue web url|website' ([ed6c1c5](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/ed6c1c57cfd97f9fad68ebdf65f5e13641942b74))
* **ingestion:** add chunking options to CLI and YAML config; wrap sources via ChunkingSource for per-chunk indexing ([b15dca1](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/b15dca1301bdd7f273d7ad83cacbb83d7239bc21))
* **ingestion:** add modular ingestion sources (filesystem, GitHub repo/org) and YAML config-driven batch indexing; extend RAGService to index items ([6584f37](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/6584f37712ce3d0486db104e0ee017ed41b32036))
* **issues:** add GitHubIssuesSource and commands to queue/checksum/estimate indexing of repository issues ([bd3dd70](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/bd3dd702a3898a68dc7afa27970b0cd713eb959f))
* **jobs:** add Redis JobRepository and RabbitMQ placeholder; support backend selection ([8a3106b](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/8a3106b731e0c6667260dad76c33c5698864cfbc))
* **k8s,s3:** add S3 artifact store and staging backend switch; add optional HTTP health server; provide Kubernetes manifests for bot and worker ([8779520](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/8779520ee03133215b081f705713a734fa63e0cf))
* **lang:** detect user language and pin responses to it ([b9c5aa4](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/b9c5aa45ed9519ab26701e8c9e4fbf127a13e903))
* **memory:** introduce abstract MemoryService and LlamaIndex-backed persistent chat memory with fallback ([06a910b](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/06a910b27a010b076f306e1e756ed7a8d4681541))
* **metrics:** expose Prometheus /metrics and instrument RAG, Discord, jobs, indexing; refactor configs; remove Redis backend support ([862ceda](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/862ceda9ea9598b5950b49366198fc9f2848856f))
* **orm:** add SQLAlchemy ORM models and session helpers (settings, checksums, dynamic chunk table); auto-migrate prompts at startup ([a1b4b79](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/a1b4b79b377a19f845695f5c06b71fa29f0ee515))
* **progress:** add job progress columns + update API; propagate indexing progress to queue worker and immediate '/index' commands with live updates ([00a8958](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/00a8958096bdd9e9131f250d2d5f59c7bb4eebaf))
* **prompt:** add per-guild and per-channel system prompt overrides with admin commands; use effective prompt at query time; ignore .staging in git ([c19a09d](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/c19a09da94ba9beaf37ccceb184ab0dfa71a62b2))
* **providers:** add vLLM provider (OpenAI-compatible) with selectable embedding backend; docs and env updates ([c6679eb](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/c6679eb63fe984c81024d2f3c5da6d46c432b750))
* **prune:** add /queue prune subcommands and worker support to delete stale vector rows scoped by manifest ([1509f71](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/1509f71cfef154782acf45fe0a521ab440fc9416))
* **queue:** add '/queue list' and '/queue show <id>' subcommands; implement async list/get in JobStore with timestamps ([6aa5324](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/6aa5324a4293c06a41edb0d64525ef29ba15c405))
* **queue:** add Discord commands to enqueue indexing jobs and a queue worker CLI; persist jobs in Postgres with JSON payloads ([bcf3df4](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/bcf3df481e335060e52130abcea4c4d8480aeeb7))
* **queue:** add sitemap subcommands for web and checksum workflows ([3c1d213](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/3c1d213e5da92468745b4c79f876017e6ddd3a94))
* **queue:** implement RabbitMQ hybrid JobRepository (Postgres persistence + RabbitMQ dispatch) for scalable workers ([0ea8ee2](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/0ea8ee2b68c9c1231701a30982ff934038bac24d))
* **queue:** support queue-type-aware workers and job repo factory ([35a2c4c](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/35a2c4c40957344d23410c0e841f3e7bd7202b0e))
* **rag:** add configurable LLM fallback/mix; disable prefix commands and rely on slash + mention/reply; document env flags ([3ec888c](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/3ec888c9b19044516fa116792fbfbf77018bd34f))
* **rag:** add score-based mixing threshold (similarity|distance); add tools registry scaffolding for future tool invocation; document env ([f864bfd](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/f864bfdfd37f62733bc80b8c690f478bfa4574aa))
* **rag:** expose best retrieval score; add LLM-only answer helper ([b37f57b](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/b37f57b8b723907339ccbfb3c99639f514f65b7b))
* **rag:** fallback to plain LLM answers when vector store is empty; cache row count and update on indexing ([3fe215b](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/3fe215be22fa05019f6bb5067f3267b7e1ed8bbf))
* **release:** add semantic-release + chart-releaser and bump versions without sed ([1d78b8e](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/1d78b8e42c41590a50b0b04940d76d4265360b6f))
* **safety:** verify pgvector embedding dimension at startup; raise clear error with remediation steps when mismatched ([1b17be8](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/1b17be86913218ebc31d0e0f4eb3f3408a121720))
* **stats:** add /stats rag_size admin command to show RAG footprint ([32667b4](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/32667b4740f2541c756a1852c5920c23189221cc))

### Bug Fixes

* **bot:** avoid duplicate slash command registration by removing manual add/remove in cogs ([aba5ee3](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/aba5ee366d4e62d32bc2194784c676081f6de417))
* **bot:** remove unsupported CommandTree.add_check; restrict commands by copying to whitelisted guilds and clearing global ([5f248bc](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/5f248bc140d061704163b746c2df07775eb3be49))
* **chat:** use async context manager for typing indicator to prevent AttributeError ([fec44dc](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/fec44dc900e6735baa4995f52c2e61df48d0d585))
* **commands/memory:** fetch memory context via asyncio.to_thread to avoid awaiting issues inside event loop ([4174e01](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/4174e014cf9bea8651a4dec046a3856405635da1))
* **commands:** ensure grouped slash commands are registered in app command tree ([7d73548](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/7d7354856644ddb11955108ca3ee066c38890d0a))
* **deps:** correct pyproject dependency list ([7f50f2e](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/7f50f2e4c18161668c3d40212c8385eb3168ab14))
* **estimate:** run estimation in thread with sync helper (avoid coroutine returned to to_thread) ([ace5913](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/ace5913072d3763958885793b11a66ebd093489f))
* **github:** ensure labels list when fetching issues ([6ce757d](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/6ce757d1f5c85c63c71e92679084b8dfaee36309))
* **jobrepo:** import Db from rag_core.types ([2632ae2](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/2632ae2f20936460bef1a9a3abc6002815dd4c52))
* **memory:** avoid 'coroutine was never awaited' by scheduling DB writes in background and running clear() via thread ([e1d36f2](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/e1d36f23df7659049c7b407e02e6a26be226c1ff))
* **memory:** run update_summary in background thread to avoid event-loop coroutine warnings ([69f0fd6](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/69f0fd6e6db5635b3d8764e170169e52a4b4727f))
* **ollama:** implement create_llm factory; honor base_url ([10229df](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/10229df668d4499e118e542150ac5610446d438e))
* **queue:** correct indentation and dynamic SQL placeholders in JobStore; resolve IndentationError ([8cd505d](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/8cd505d927125b6093f137bce3584869299c7b79))
* **queue:** provide async enqueue method and use it in Discord commands to avoid asyncio.run inside event loop ([d3a28b9](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/d3a28b912f8244abec70b352be2e3615dc10bc4d))
* **queue:** remove asyncpg.types.Json dependency; use json.dumps for JSONB insert and robust payload decoding on fetch ([58316c5](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/58316c5a539e5f8db110ef4227aa7ac10065df5b))
* **queue:** wrap JSON payload with asyncpg.types.Json to store dicts into JSONB ([546fa53](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/546fa5319d9fe3107c3e4ebd7095f332eaa0bdbb))
* **stats:** cast metadata to JSONB before jsonb_extract_path_text ([715ca1d](https://github.com/OneLiteFeatherNET/OneLiteFeatherRAGBot/commit/715ca1de1bc85e97d26a8da35eb472cab0e0cefa))

# Changelog

All notable changes to this project will be documented in this file by semantic-release.
