from __future__ import annotations

from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands
import json
from ..util.text import clip_discord_message
from ..config import settings
from rag_core.ingestion.web import UrlSource, WebsiteCrawlerSource


def _split_list(csv: Optional[str]) -> Optional[List[str]]:
    if not csv:
        return None
    return [s.strip() for s in csv.split(",") if s.strip()]


class IndexQueueCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    queue = app_commands.Group(name="queue", description="Manage indexing jobs", default_permissions=discord.Permissions(administrator=True))
    github = app_commands.Group(name="github", description="GitHub sources", parent=queue)
    local = app_commands.Group(name="local", description="Local filesystem sources", parent=queue)
    web = app_commands.Group(name="web", description="Web sources (URLs, crawl)", parent=queue)

    @staticmethod
    def admin_check():
        async def predicate(interaction: discord.Interaction) -> bool:
            if isinstance(interaction.user, discord.Member):
                return interaction.user.guild_permissions.administrator
            return False
        return app_commands.check(predicate)

    @github.command(name="repo", description="Queue a GitHub repository for indexing")
    @admin_check.__func__()
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
    ):
        await interaction.response.defer(ephemeral=True)
        payload = {
            "sources": [
                {
                    "type": "github_repo",
                    "repo": repo,
                    "branch": branch,
                    "exts": _split_list(exts) or settings.ingest_exts,
                }
            ],
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        job_id = await self.bot.services.job_store.enqueue_async("ingest", payload)  # type: ignore[attr-defined]
        await interaction.followup.send(f"Queued job #{job_id} for repo {repo}", ephemeral=True)

    @github.command(name="org", description="Queue all repos in a GitHub org for indexing")
    @admin_check.__func__()
    @app_commands.describe(
        org="GitHub organization name",
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
    ):
        await interaction.response.defer(ephemeral=True)
        payload = {
            "sources": [
                {
                    "type": "github_org",
                    "org": org,
                    "visibility": visibility,
                    "include_archived": include_archived,
                    "topics": _split_list(topics),
                    "exts": _split_list(exts) or settings.ingest_exts,
                    "branch": branch,
                }
            ],
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        job_id = await self.bot.services.job_store.enqueue_async("ingest", payload)  # type: ignore[attr-defined]
        await interaction.followup.send(f"Queued job #{job_id} for org {org}", ephemeral=True)

    @local.command(name="dir", description="Queue a local directory for indexing")
    @admin_check.__func__()
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
    ):
        await interaction.response.defer(ephemeral=True)
        payload = {
            "sources": [
                {
                    "type": "local_dir",
                    "path": repo_root,
                    "repo_url": repo_url,
                    "exts": _split_list(exts) or settings.ingest_exts,
                }
            ],
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        job_id = await self.bot.services.job_store.enqueue_async("ingest", payload)  # type: ignore[attr-defined]
        await interaction.followup.send(f"Queued job #{job_id} for path {repo_root}", ephemeral=True)

    @queue.command(name="list", description="List recent indexing jobs")
    @admin_check.__func__()
    @app_commands.describe(status="Optional status filter (pending|processing|completed|failed)", limit="Max number of jobs to list (default 20)")
    async def list_jobs(self, interaction: discord.Interaction, status: Optional[str] = None, limit: int = 20):
        await interaction.response.defer(ephemeral=True)
        jobs = await self.bot.services.job_store.list_jobs_async(limit=limit, status=status)  # type: ignore[attr-defined]
        if not jobs:
            await interaction.followup.send("No jobs found.", ephemeral=True)
            return
        lines = []
        for j in jobs:
            created = j.created_at.isoformat() if j.created_at else "-"
            lines.append(f"#{j.id} {j.status} {j.type} attempts={j.attempts} created={created}")
        await interaction.followup.send(clip_discord_message("Jobs:\n" + "\n".join(lines)), ephemeral=True)

    @queue.command(name="show", description="Show details of a job")
    @admin_check.__func__()
    @app_commands.describe(job_id="Job ID")
    async def show_job(self, interaction: discord.Interaction, job_id: int):
        await interaction.response.defer(ephemeral=True)
        j = await self.bot.services.job_store.get_job_async(job_id)  # type: ignore[attr-defined]
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
    @admin_check.__func__()
    @app_commands.describe(urls="Comma-separated list of URLs")
    async def web_url(self, interaction: discord.Interaction, urls: str):
        await interaction.response.defer(ephemeral=True)
        url_list = [u.strip() for u in urls.split(",") if u.strip()]
        payload = {"sources": [{"type": "web_url", "urls": url_list}]}
        job_id = await self.bot.services.job_store.enqueue_async("ingest", payload)  # type: ignore[attr-defined]
        await interaction.followup.send(f"Queued job #{job_id} for {len(url_list)} URLs", ephemeral=True)

    @web.command(name="website", description="Queue a website crawl for indexing")
    @admin_check.__func__()
    @app_commands.describe(start_url="Start URL", allowed_prefixes="Comma-separated URL prefixes", max_pages="Max pages to crawl (default 200)")
    async def web_site(self, interaction: discord.Interaction, start_url: str, allowed_prefixes: str = "", max_pages: int = 200):
        await interaction.response.defer(ephemeral=True)
        prefixes = [p.strip() for p in allowed_prefixes.split(",") if p.strip()] or [start_url]
        payload = {
            "sources": [
                {
                    "type": "website",
                    "start_urls": [start_url],
                    "allowed_prefixes": prefixes,
                    "max_pages": max_pages,
                }
            ]
        }
        job_id = await self.bot.services.job_store.enqueue_async("ingest", payload)  # type: ignore[attr-defined]
        await interaction.followup.send(f"Queued job #{job_id} to crawl {start_url}", ephemeral=True)

    @queue.command(name="retry", description="Retry a failed or canceled job")
    @admin_check.__func__()
    @app_commands.describe(job_id="Job ID to retry")
    async def retry_job(self, interaction: discord.Interaction, job_id: int):
        await interaction.response.defer(ephemeral=True)
        ok = await self.bot.services.job_store.retry_async(job_id)  # type: ignore[attr-defined]
        if ok:
            await interaction.followup.send(f"Job #{job_id} moved to pending.", ephemeral=True)
        else:
            await interaction.followup.send(f"Job #{job_id} not eligible for retry.", ephemeral=True)

    @queue.command(name="cancel", description="Cancel a pending/processing job (best-effort)")
    @admin_check.__func__()
    @app_commands.describe(job_id="Job ID to cancel")
    async def cancel_job(self, interaction: discord.Interaction, job_id: int):
        await interaction.response.defer(ephemeral=True)
        ok = await self.bot.services.job_store.cancel_async(job_id)  # type: ignore[attr-defined]
        if ok:
            await interaction.followup.send(f"Job #{job_id} canceled.", ephemeral=True)
        else:
            await interaction.followup.send(f"Job #{job_id} not cancelable (maybe already completed or failed).", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(IndexQueueCog(bot))
