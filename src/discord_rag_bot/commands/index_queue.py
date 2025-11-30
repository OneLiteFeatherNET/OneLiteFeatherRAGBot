from __future__ import annotations

from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands
import json
from ..util.text import clip_discord_message
from ..config import settings
from ..infrastructure.permissions import require_admin
from rag_core.ingestion.web import UrlSource, WebsiteCrawlerSource
from rag_core.ingestion.web import SitemapSource
from rag_core.ingestion.github import GitRepoSource, GitHubOrgSource, GitHubIssuesSource
from rag_core.ingestion.filesystem import FilesystemSource
from rag_core.ingestion.chunked import ChunkingSource
from rag_core.etl.artifacts import LocalArtifactStore
from rag_core.etl.artifacts_s3 import S3ArtifactStore, S3Unavailable
from rag_core.etl.pipeline import build_manifest
from pathlib import Path
from rag_core.metrics import jobs_enqueued_total


def _split_list(csv: Optional[str]) -> Optional[List[str]]:
    if not csv:
        return None
    return [s.strip() for s in csv.split(",") if s.strip()]


class IndexQueueCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    queue = app_commands.Group(name="queue", description="Manage indexing jobs", default_permissions=discord.Permissions(administrator=True))
    github = app_commands.Group(name="github", description="GitHub sources", parent=queue)
    suggest = app_commands.Group(name="suggest", description="Suggestions", parent=queue)
    local = app_commands.Group(name="local", description="Local filesystem sources", parent=queue)
    web = app_commands.Group(name="web", description="Web sources (URLs, crawl)", parent=queue)
    checksum = app_commands.Group(name="checksum", description="Checksum-only update jobs", parent=queue)
    prune = app_commands.Group(name="prune", description="Prune entfernte Inhalte anhand eines Manifests", parent=queue)

    def _artifact_store(self):
        backend = (getattr(settings, "etl_staging_backend", "local") or "local").lower()
        if backend == "s3":
            if not getattr(settings, "s3_staging_bucket", None):
                raise RuntimeError("S3 staging selected but APP_S3_STAGING_BUCKET not set")
            try:
                return S3ArtifactStore(
                    bucket=settings.s3_staging_bucket,  # type: ignore[arg-type]
                    prefix=getattr(settings, "s3_staging_prefix", "rag-artifacts"),
                    region=getattr(settings, "s3_region", None),
                    endpoint_url=getattr(settings, "s3_endpoint_url", None),
                    access_key_id=getattr(settings, "s3_access_key_id", None),
                    secret_access_key=getattr(settings, "s3_secret_access_key", None),
                )
            except S3Unavailable as e:
                raise RuntimeError(str(e))
        # default local
        from pathlib import Path as _Path
        return LocalArtifactStore(root=_Path(getattr(settings, "etl_staging_dir", ".staging")))

    async def _watch_job(self, message: discord.Message, job_id: int):
        import asyncio
        poll = max(1.0, float(getattr(settings, "queue_watch_poll_sec", 5.0)))
        while True:
            j = await self.bot.services.job_repo_default.get(job_id)  # type: ignore[attr-defined]
            if not j:
                await message.edit(content=f"Job #{job_id} not found anymore.")
                return
            progress = ""
            if j.progress_done is not None or j.progress_total is not None:
                progress = f" ({j.progress_done or 0}/{j.progress_total or '?'})"
            note = f" – {j.progress_note}" if j.progress_note else ""
            await message.edit(content=f"Job #{job_id}: {j.status}{progress}{note}")
            if j.status in ("completed", "failed", "canceled"):
                return
            await asyncio.sleep(poll)

    @staticmethod
    def admin_check():
        async def predicate(interaction: discord.Interaction) -> bool:
            if isinstance(interaction.user, discord.Member):
                return interaction.user.guild_permissions.administrator
            return False
        return app_commands.check(predicate)

    @github.command(name="repo", description="Queue a GitHub repository for indexing (local clone preferred)")
    @require_admin()
    @app_commands.describe(
        repo="GitHub repo URL (e.g., https://github.com/ORG/REPO)",
        branch="Optional branch (default: default branch)",
        exts="Comma-separated file extensions (e.g., .md,.py)",
        chunk_size="Optional chunk size (characters)",
        chunk_overlap="Optional chunk overlap (characters)",
    )
    async def github_repo(
        self,
        interaction: discord.Interaction,
        repo: str,
        branch: Optional[str] = None,
        exts: Optional[str] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = 200,
        force: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        exts_list = _split_list(exts) or settings.ingest_exts
        # Prefer local clone on worker for full repo indexing to avoid API limits
        cfg: dict = {
            "sources": [
                {
                    "type": "github_repo_local",
                    "repo": repo,
                    **({"branch": branch} if branch else {}),
                    **({"exts": exts_list} if exts_list else {}),
                    "shallow": True,
                    "fetch_depth": 50,
                }
            ]
        }
        if chunk_size:
            cfg["chunk_size"] = int(chunk_size)
            cfg["chunk_overlap"] = int(chunk_overlap or 200)
        if force:
            cfg["force"] = True
        job_id = await self.bot.services.job_repo_factory.get("ingest").enqueue("ingest", cfg)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="ingest").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (github repo local clone)")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued job #{job_id} for repo {repo} (local clone)", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @github.command(name="issues", description="Queue GitHub Issues eines Repos für das RAG")
    @require_admin()
    @app_commands.describe(
        repo="GitHub repo URL (z. B. https://github.com/ORG/REPO)",
        state="Filter: all|open|closed (default: all)",
        labels="Kommagetrennte Labels (Subset-Filter)",
        include_comments="Kommentare mit indizieren",
        chunk_size="Optional chunk size (characters)",
        chunk_overlap="Optional chunk overlap (characters)",
    )
    async def github_issues(
        self,
        interaction: discord.Interaction,
        repo: str,
        state: str = "all",
        labels: Optional[str] = None,
        include_comments: bool = True,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = 200,
    ):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Building manifest (GitHub issues)…", ephemeral=True)
        src: object = GitHubIssuesSource(repo_url=repo, state=state, labels=_split_list(labels), include_comments=include_comments)
        if chunk_size:
            src = ChunkingSource(source=src, chunk_size=chunk_size or 0, overlap=chunk_overlap or 200)  # type: ignore[arg-type]
        manifest = await __import__("asyncio").to_thread(build_manifest, src)  # type: ignore[arg-type]
        store = self._artifact_store()
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key}
        job_id = await self.bot.services.job_repo_factory.get("ingest").enqueue("ingest", payload)  # type: ignore[attr-defined]
        msg = await interaction.channel.send(f"Job #{job_id}: queued (github issues {repo}, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued job #{job_id} for issues in {repo}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @github.command(name="org", description="Queue all repositories for a GitHub organization or user (name or URL)")
    @require_admin()
    @app_commands.describe(
        org="GitHub organization or user (name or URL)",
        visibility="Visibility filter (all|public|private)",
        include_archived="Include archived repos",
        topics="Comma-separated topics to filter (subset)",
        branch="Optional branch",
        exts="Comma-separated file extensions",
        chunk_size="Optional chunk size",
        chunk_overlap="Optional chunk overlap",
    )
    async def github_org(
        self,
        interaction: discord.Interaction,
        org: str,
        visibility: str = "all",
        include_archived: bool = False,
        topics: Optional[str] = None,
        branch: Optional[str] = None,
        exts: Optional[str] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = 200,
        force: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        exts_list = _split_list(exts) or settings.ingest_exts
        await interaction.followup.send("Listing organization repositories…", ephemeral=True)
        src_org = GitHubOrgSource(org=org, visibility=visibility, include_archived=include_archived, topics=_split_list(topics), exts=exts_list, branch=branch)
        try:
            urls = src_org._list_repo_urls()
        except Exception as e:
            await interaction.followup.send(
                f"❌ Could not list repositories for '{org}': {e}.\n"
                "Make sure the organization exists and that GITHUB_TOKEN has access, or try indexing a single repo via /queue github repo.",
                ephemeral=True,
            )
            return
        if not urls:
            await interaction.followup.send("(no repositories found)", ephemeral=True)
            return
        # Enqueue one job per repo, prefer local clone to avoid API limits
        enq = self.bot.services.job_repo_factory.get("ingest").enqueue  # type: ignore[attr-defined]
        job_ids: list[int] = []
        for u in urls:
            cfg = {
                "sources": [
                    {
                        "type": "github_repo_local",
                        "repo": u,
                        **({"branch": branch} if branch else {}),
                        **({"exts": exts_list} if exts_list else {}),
                        "shallow": True,
                        "fetch_depth": 50,
                    }
                ]
            }
            if chunk_size:
                cfg["chunk_size"] = int(chunk_size)
                cfg["chunk_overlap"] = int(chunk_overlap or 200)
            if force:
                cfg["force"] = True
            jid = await enq("ingest", cfg)
            try:
                jobs_enqueued_total.labels(type="ingest").inc()
            except Exception:
                pass
            job_ids.append(int(jid))
        msg = await interaction.channel.send(f"Queued {len(job_ids)} jobs for org {org}")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued {len(job_ids)} repos from {org}", ephemeral=True)

    @local.command(name="dir", description="Queue a local directory for indexing")
    @require_admin()
    @app_commands.describe(
        repo_root="Local path to repository root on the indexer host",
        repo_url="Public URL used for source links",
        exts="Comma-separated file extensions",
        chunk_size="Optional chunk size",
        chunk_overlap="Optional chunk overlap",
    )
    async def local_dir(
        self,
        interaction: discord.Interaction,
        repo_root: str,
        repo_url: str,
        exts: Optional[str] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = 200,
        force: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        exts_list = _split_list(exts) or settings.ingest_exts
        await interaction.followup.send("Building manifest (local dir)…", ephemeral=True)
        source: object = FilesystemSource(repo_root=Path(repo_root), repo_url=repo_url, exts=exts_list)
        if chunk_size:
            source = ChunkingSource(source=source, chunk_size=chunk_size or 0, overlap=chunk_overlap or 200)  # type: ignore[arg-type]
        manifest = await __import__("asyncio").to_thread(build_manifest, source)  # type: ignore[arg-type]
        store = self._artifact_store()
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key}
        if force:
            payload["force"] = True
        job_id = await self.bot.services.job_repo_factory.get("ingest").enqueue("ingest", payload)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="ingest").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (local dir {repo_root}, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued job #{job_id} for path {repo_root}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @queue.command(name="list", description="List recent indexing jobs")
    @require_admin()
    @app_commands.describe(status="Optional status filter (pending|processing|completed|failed)", limit="Max number of jobs to list (default 20)")
    async def list_jobs(self, interaction: discord.Interaction, status: Optional[str] = None, limit: int = 20):
        await interaction.response.defer(ephemeral=True)
        jobs = await self.bot.services.job_repo_default.list(limit=limit, status=status)  # type: ignore[attr-defined]
        if not jobs:
            await interaction.followup.send("No jobs found.", ephemeral=True)
            return
        lines = []
        for j in jobs:
            created = j.created_at.isoformat() if j.created_at else "-"
            lines.append(f"#{j.id} {j.status} {j.type} attempts={j.attempts} created={created}")
        await interaction.followup.send(clip_discord_message("Jobs:\n" + "\n".join(lines)), ephemeral=True)

    @queue.command(name="show", description="Show details of a job")
    @require_admin()
    @app_commands.describe(job_id="Job ID")
    async def show_job(self, interaction: discord.Interaction, job_id: int):
        await interaction.response.defer(ephemeral=True)
        j = await self.bot.services.job_repo_default.get(job_id)  # type: ignore[attr-defined]
        if not j:
            await interaction.followup.send(f"Job #{job_id} not found.", ephemeral=True)
            return
        payload = json.dumps(j.payload, indent=2, ensure_ascii=False)
        text = (
            f"Job #{j.id} [{j.status}]\n"
            f"type: {j.type}\n"
            f"attempts: {j.attempts}\n"
            f"created: {j.created_at}\n"
            f"started: {j.started_at}\n"
            f"finished: {j.finished_at}\n"
            f"error: {j.error or '-'}\n\n"
            f"payload:\n```json\n{payload}\n```"
        )
        await interaction.followup.send(clip_discord_message(text), ephemeral=True)

    @web.command(name="url", description="Queue specific URLs for indexing")
    @require_admin()
    @app_commands.describe(urls="Comma-separated list of URLs", force="Force re-index (ignore checksums)")
    async def web_url(self, interaction: discord.Interaction, urls: str, force: bool = False):
        await interaction.response.defer(ephemeral=True)
        url_list = [u.strip() for u in urls.split(",") if u.strip()]
        await interaction.followup.send("Building manifest (URLs)…", ephemeral=True)
        source = UrlSource(urls=url_list)
        manifest = await __import__("asyncio").to_thread(build_manifest, source)
        store = self._artifact_store()
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key}
        if force:
            payload["force"] = True
        job_id = await self.bot.services.job_repo_factory.get("ingest").enqueue("ingest", payload)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="ingest").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (web url, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued job #{job_id} for {len(url_list)} URLs", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @web.command(name="website", description="Queue a website crawl for indexing")
    @require_admin()
    @app_commands.describe(start_url="Start URL", allowed_prefixes="Comma-separated URL prefixes", max_pages="Max pages to crawl (default 200)", force="Force re-index (ignore checksums)")
    async def web_site(self, interaction: discord.Interaction, start_url: str, allowed_prefixes: str = "", max_pages: int = 200, force: bool = False):
        await interaction.response.defer(ephemeral=True)
        prefixes = [p.strip() for p in allowed_prefixes.split(",") if p.strip()] or [start_url]
        await interaction.followup.send("Building manifest (website)…", ephemeral=True)
        source = WebsiteCrawlerSource(start_urls=[start_url], allowed_prefixes=prefixes, max_pages=max_pages)
        manifest = await __import__("asyncio").to_thread(build_manifest, source)
        store = self._artifact_store()
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key}
        if force:
            payload["force"] = True
        job_id = await self.bot.services.job_repo_factory.get("ingest").enqueue("ingest", payload)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="ingest").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (website {start_url}, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued job #{job_id} to crawl {start_url}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @web.command(name="sitemap", description="Queue a sitemap for indexing")
    @require_admin()
    @app_commands.describe(sitemap_url="Sitemap URL (XML)", limit="Optional limit of URLs to fetch", force="Force re-index (ignore checksums)")
    async def web_sitemap(self, interaction: discord.Interaction, sitemap_url: str, limit: Optional[int] = None, force: bool = False):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Building manifest (sitemap)…", ephemeral=True)
        source = SitemapSource(sitemap_url=sitemap_url, limit=limit)
        manifest = await __import__("asyncio").to_thread(build_manifest, source)
        store = LocalArtifactStore(root=Path(getattr(settings, "etl_staging_dir", ".staging")))
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key}
        if force:
            payload["force"] = True
        job_id = await self.bot.services.job_repo_factory.get("ingest").enqueue("ingest", payload)  # type: ignore[attr-defined]
        msg = await interaction.channel.send(f"Job #{job_id}: queued (sitemap {sitemap_url}, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued job #{job_id} for sitemap {sitemap_url}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    # Suggestions: list known repos and hint to re-index
    @suggest.command(name="repos", description="List known repositories from the index with last update timestamps")
    @app_commands.describe(limit="Max repositories to list (default 10)")
    async def suggest_repos(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        try:
            from ..tools.repo_tools import _group_repos_from_checksums
            items = _group_repos_from_checksums()[: max(1, int(limit))]
            if not items:
                await interaction.followup.send("(no repositories found)", ephemeral=True)
                return
            lines = ["Known repositories (latest first):"]
            for repo, count, last in items:
                lines.append(f"- {repo} (docs: {count}, last: {last or '-'})")
            lines.append("\nRe-index via: /queue github repo repo:<url> [branch] [exts] …")
            await interaction.followup.send(clip_discord_message("\n".join(lines)), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed to list repositories: {e}", ephemeral=True)

    # Checksum-only jobs (ETL manifest built, then queued as checksum_update)
    @checksum.command(name="github_repo", description="Queue checksum-only update for a GitHub repository")
    @require_admin()
    @app_commands.describe(repo="GitHub repo URL", branch="Optional branch", exts="Comma-separated extensions")
    async def checksum_github_repo(self, interaction: discord.Interaction, repo: str, branch: Optional[str] = None, exts: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        exts_list = _split_list(exts) or settings.ingest_exts
        await interaction.followup.send("Building manifest (GitHub repo)…", ephemeral=True)
        source: object = GitRepoSource(repo_url=repo, branch=branch, exts=exts_list)
        manifest = await __import__("asyncio").to_thread(build_manifest, source)  # type: ignore[arg-type]
        store = LocalArtifactStore(root=Path(getattr(settings, "etl_staging_dir", ".staging")))
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key}
        job_id = await self.bot.services.job_repo_factory.get("checksum_update").enqueue("checksum_update", payload)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="checksum_update").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (checksum github repo, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued checksum-update job #{job_id} for repo {repo}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @checksum.command(name="github_issues", description="Checksum-Update nur für GitHub Issues eines Repos")
    @require_admin()
    @app_commands.describe(repo="GitHub repo URL", state="all|open|closed", labels="Labels", include_comments="Kommentare einbeziehen")
    async def checksum_github_issues(self, interaction: discord.Interaction, repo: str, state: str = "all", labels: Optional[str] = None, include_comments: bool = True):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Building manifest (GitHub issues)…", ephemeral=True)
        src = GitHubIssuesSource(repo_url=repo, state=state, labels=_split_list(labels), include_comments=include_comments)
        manifest = await __import__("asyncio").to_thread(build_manifest, src)
        store = self._artifact_store()
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key}
        job_id = await self.bot.services.job_repo_factory.get("checksum_update").enqueue("checksum_update", payload)  # type: ignore[attr-defined]
        msg = await interaction.channel.send(f"Job #{job_id}: queued (checksum github issues, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued checksum-update job #{job_id} for issues in {repo}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @checksum.command(name="local_dir", description="Queue checksum-only update for a local directory")
    @admin_check.__func__()
    @app_commands.describe(repo_root="Local path", repo_url="Public URL for links", exts="Comma-separated extensions")
    async def checksum_local_dir(self, interaction: discord.Interaction, repo_root: str, repo_url: str, exts: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        exts_list = _split_list(exts) or settings.ingest_exts
        await interaction.followup.send("Building manifest (local dir)…", ephemeral=True)
        source: object = FilesystemSource(repo_root=Path(repo_root), repo_url=repo_url, exts=exts_list)
        manifest = await __import__("asyncio").to_thread(build_manifest, source)  # type: ignore[arg-type]
        store = LocalArtifactStore(root=Path(getattr(settings, "etl_staging_dir", ".staging")))
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key}
        job_id = await self.bot.services.job_repo_factory.get("checksum_update").enqueue("checksum_update", payload)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="checksum_update").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (checksum local dir {repo_root}, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued checksum-update job #{job_id} for path {repo_root}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @checksum.command(name="web_url", description="Queue checksum-only update for specific URLs")
    @admin_check.__func__()
    @app_commands.describe(urls="Comma-separated list of URLs")
    async def checksum_web_url(self, interaction: discord.Interaction, urls: str):
        await interaction.response.defer(ephemeral=True)
        url_list = [u.strip() for u in urls.split(",") if u.strip()]
        await interaction.followup.send("Building manifest (URLs)…", ephemeral=True)
        source = UrlSource(urls=url_list)
        manifest = await __import__("asyncio").to_thread(build_manifest, source)
        store = LocalArtifactStore(root=Path(getattr(settings, "etl_staging_dir", ".staging")))
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key}
        job_id = await self.bot.services.job_repo_factory.get("checksum_update").enqueue("checksum_update", payload)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="checksum_update").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (checksum web url, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued checksum-update job #{job_id} for {len(url_list)} URLs", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @checksum.command(name="website", description="Queue checksum-only update for a website section")
    @admin_check.__func__()
    @app_commands.describe(start_url="Start URL", allowed_prefixes="Comma-separated prefixes", max_pages="Max pages to crawl")
    async def checksum_website(self, interaction: discord.Interaction, start_url: str, allowed_prefixes: str = "", max_pages: int = 200):
        await interaction.response.defer(ephemeral=True)
        prefixes = [p.strip() for p in allowed_prefixes.split(",") if p.strip()] or [start_url]
        await interaction.followup.send("Building manifest (website)…", ephemeral=True)
        source = WebsiteCrawlerSource(start_urls=[start_url], allowed_prefixes=prefixes, max_pages=max_pages)
        manifest = await __import__("asyncio").to_thread(build_manifest, source)
        store = LocalArtifactStore(root=Path(getattr(settings, "etl_staging_dir", ".staging")))
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key}
        job_id = await self.bot.services.job_repo_factory.get("checksum_update").enqueue("checksum_update", payload)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="checksum_update").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (checksum website {start_url}, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued checksum-update job #{job_id} to crawl {start_url}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @checksum.command(name="sitemap", description="Queue checksum-only update for a sitemap")
    @admin_check.__func__()
    @app_commands.describe(sitemap_url="Sitemap URL (XML)", limit="Optional limit of URLs to fetch")
    async def checksum_sitemap(self, interaction: discord.Interaction, sitemap_url: str, limit: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Building manifest (sitemap)…", ephemeral=True)
        source = SitemapSource(sitemap_url=sitemap_url, limit=limit)
        manifest = await __import__("asyncio").to_thread(build_manifest, source)
        store = LocalArtifactStore(root=Path(getattr(settings, "etl_staging_dir", ".staging")))
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key}
        job_id = await self.bot.services.job_repo_factory.get("checksum_update").enqueue("checksum_update", payload)  # type: ignore[attr-defined]
        msg = await interaction.channel.send(f"Job #{job_id}: queued (checksum sitemap, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued checksum-update job #{job_id} for sitemap {sitemap_url}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    # ------------------- PRUNE COMMANDS -------------------
    # Entfernt Vektoreinträge, die nicht im aktuellen Manifest enthalten sind (scoped).

    @prune.command(name="github_repo", description="Prune für ein GitHub-Repository (entfernt nicht mehr vorhandene Dateien)")
    @admin_check.__func__()
    @app_commands.describe(repo="GitHub repo URL", branch="Optionaler Branch", exts="Kommagetrennte Endungen", chunk_size="Chunkgröße", chunk_overlap="Overlap")
    async def prune_github_repo(self, interaction: discord.Interaction, repo: str, branch: Optional[str] = None, exts: Optional[str] = None, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = 200):
        await interaction.response.defer(ephemeral=True)
        exts_list = _split_list(exts) or settings.ingest_exts
        await interaction.followup.send("Building manifest (GitHub repo)…", ephemeral=True)
        source: object = GitRepoSource(repo_url=repo, branch=branch, exts=exts_list)
        if chunk_size:
            source = ChunkingSource(source=source, chunk_size=chunk_size or 0, overlap=chunk_overlap or 200)  # type: ignore[arg-type]
        manifest = await __import__("asyncio").to_thread(build_manifest, source)  # type: ignore[arg-type]
        store = self._artifact_store()
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key, "prune_scope": {"metadata_repo_in": [repo]}}
        job_id = await self.bot.services.job_repo_factory.get("prune").enqueue("prune", payload)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="prune").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (prune github repo, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued prune job #{job_id} for repo {repo}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @prune.command(name="local_dir", description="Prune für lokales Verzeichnis (entfernt nicht mehr vorhandene Dateien)")
    @admin_check.__func__()
    @app_commands.describe(repo_root="Lokaler Pfad", repo_url="Öffentliche URL", exts="Kommagetrennte Endungen", chunk_size="Chunkgröße", chunk_overlap="Overlap")
    async def prune_local_dir(self, interaction: discord.Interaction, repo_root: str, repo_url: str, exts: Optional[str] = None, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = 200):
        await interaction.response.defer(ephemeral=True)
        exts_list = _split_list(exts) or settings.ingest_exts
        await interaction.followup.send("Building manifest (local dir)…", ephemeral=True)
        source: object = FilesystemSource(repo_root=Path(repo_root), repo_url=repo_url, exts=exts_list)
        if chunk_size:
            source = ChunkingSource(source=source, chunk_size=chunk_size or 0, overlap=chunk_overlap or 200)  # type: ignore[arg-type]
        manifest = await __import__("asyncio").to_thread(build_manifest, source)  # type: ignore[arg-type]
        store = self._artifact_store()
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key, "prune_scope": {"metadata_repo_in": [repo_url]}}
        job_id = await self.bot.services.job_repo_factory.get("prune").enqueue("prune", payload)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="prune").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (prune local dir, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued prune job #{job_id} for path {repo_root}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @prune.command(name="github_org", description="Prune für eine GitHub-Organisation (nach Themen/Archivier-Status filterbar)")
    @admin_check.__func__()
    @app_commands.describe(org="Org", visibility="all|public|private", include_archived="Archivierte einbeziehen", topics="Kommagetrennt", branch="Branch", exts="Endungen", chunk_size="Chunkgröße", chunk_overlap="Overlap")
    async def prune_github_org(self, interaction: discord.Interaction, org: str, visibility: str = "all", include_archived: bool = False, topics: Optional[str] = None, branch: Optional[str] = None, exts: Optional[str] = None, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = 200):
        await interaction.response.defer(ephemeral=True)
        exts_list = _split_list(exts) or settings.ingest_exts
        await interaction.followup.send("Building manifest (GitHub org)…", ephemeral=True)
        source: object = GitHubOrgSource(org=org, visibility=visibility, include_archived=include_archived, topics=_split_list(topics), exts=exts_list, branch=branch)
        if chunk_size:
            source = ChunkingSource(source=source, chunk_size=chunk_size or 0, overlap=chunk_overlap or 200)  # type: ignore[arg-type]
        manifest = await __import__("asyncio").to_thread(build_manifest, source)  # type: ignore[arg-type]
        # Für Org-Prune begrenzen wir per 'metadata_repo_in' auf die Repos im Manifest (aus Metadaten extrahiert wird später im Worker)
        store = self._artifact_store()
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key, "prune_scope": {"metadata_repo_from_manifest": True}}
        job_id = await self.bot.services.job_repo_factory.get("prune").enqueue("prune", payload)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="prune").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (prune github org {org}, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued prune job #{job_id} for org {org}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @prune.command(name="web_url", description="Prune für Web-URLs (entfernt nicht mehr vorhandene URLs)")
    @admin_check.__func__()
    @app_commands.describe(urls="Kommagetrennte URLs", chunk_size="Chunkgröße", chunk_overlap="Overlap")
    async def prune_web_url(self, interaction: discord.Interaction, urls: str, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = 200):
        await interaction.response.defer(ephemeral=True)
        url_list = [u.strip() for u in urls.split(",") if u.strip()]
        await interaction.followup.send("Building manifest (URLs)…", ephemeral=True)
        source: object = UrlSource(urls=url_list)
        if chunk_size:
            source = ChunkingSource(source=source, chunk_size=chunk_size or 0, overlap=chunk_overlap or 200)  # type: ignore[arg-type]
        manifest = await __import__("asyncio").to_thread(build_manifest, source)
        store = self._artifact_store()
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key, "prune_scope": {"doc_id_in_from_manifest": True}}
        job_id = await self.bot.services.job_repo_factory.get("prune").enqueue("prune", payload)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="prune").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (prune web url, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued prune job #{job_id} for {len(url_list)} URLs", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @prune.command(name="website", description="Prune für Website-Crawl (nach Präfixen)")
    @admin_check.__func__()
    @app_commands.describe(start_url="Start URL", allowed_prefixes="Kommagetrennte Präfixe", max_pages="Max Seiten")
    async def prune_website(self, interaction: discord.Interaction, start_url: str, allowed_prefixes: str = "", max_pages: int = 200):
        await interaction.response.defer(ephemeral=True)
        prefixes = [p.strip() for p in allowed_prefixes.split(",") if p.strip()] or [start_url]
        await interaction.followup.send("Building manifest (website)…", ephemeral=True)
        source = WebsiteCrawlerSource(start_urls=[start_url], allowed_prefixes=prefixes, max_pages=max_pages)
        manifest = await __import__("asyncio").to_thread(build_manifest, source)
        store = self._artifact_store()
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key, "prune_scope": {"doc_id_prefixes": prefixes}}
        job_id = await self.bot.services.job_repo_factory.get("prune").enqueue("prune", payload)  # type: ignore[attr-defined]
        try:
            jobs_enqueued_total.labels(type="prune").inc()
        except Exception:
            pass
        msg = await interaction.channel.send(f"Job #{job_id}: queued (prune website {start_url}, manifest={key})")  # type: ignore[union-attr]
        await interaction.followup.send(f"Queued prune job #{job_id} to crawl {start_url}", ephemeral=True)
        self.bot.loop.create_task(self._watch_job(msg, job_id))

    @queue.command(name="retry", description="Retry a failed or canceled job")
    @admin_check.__func__()
    @app_commands.describe(job_id="Job ID to retry")
    async def retry_job(self, interaction: discord.Interaction, job_id: int):
        await interaction.response.defer(ephemeral=True)
        ok = await self.bot.services.job_repo_default.retry(job_id)  # type: ignore[attr-defined]
        if ok:
            await interaction.followup.send(f"Job #{job_id} moved to pending.", ephemeral=True)
        else:
            await interaction.followup.send(f"Job #{job_id} not eligible for retry.", ephemeral=True)

    @queue.command(name="cancel", description="Cancel a pending/processing job (best-effort)")
    @admin_check.__func__()
    @app_commands.describe(job_id="Job ID to cancel")
    async def cancel_job(self, interaction: discord.Interaction, job_id: int):
        await interaction.response.defer(ephemeral=True)
        ok = await self.bot.services.job_repo_default.cancel(job_id)  # type: ignore[attr-defined]
        if ok:
            await interaction.followup.send(f"Job #{job_id} canceled.", ephemeral=True)
        else:
            await interaction.followup.send(f"Job #{job_id} not cancelable (maybe already completed or failed).", ephemeral=True)


async def setup(bot: commands.Bot):
    # Register the Cog and explicitly add the grouped slash-commands to the tree
    cog = IndexQueueCog(bot)
    await bot.add_cog(cog)
    # Add top-level group; nested groups (github/local/web/checksum) are attached via parent=queue
    try:
        bot.tree.add_command(IndexQueueCog.queue)
    except Exception:
        # Ignore if already added (e.g., during hot-reload)
        pass
