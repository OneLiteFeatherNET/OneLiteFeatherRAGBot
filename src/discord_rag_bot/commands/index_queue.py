from __future__ import annotations

from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands


def _split_list(csv: Optional[str]) -> Optional[List[str]]:
    if not csv:
        return None
    return [s.strip() for s in csv.split(",") if s.strip()]


class IndexQueueCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="queue_github_repo", description="Queue a GitHub repository for indexing")
    @app_commands.describe(
        repo="GitHub repo URL (e.g., https://github.com/ORG/REPO)",
        branch="Optional branch (default: default branch)",
        exts="Comma-separated file extensions (e.g., .md,.py)",
        chunk_size="Optional chunk size (characters)",
        chunk_overlap="Optional chunk overlap (characters)",
    )
    async def queue_github_repo(
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
                    "exts": _split_list(exts),
                }
            ],
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        job_id = self.bot.services.job_store.enqueue("ingest", payload)  # type: ignore[attr-defined]
        await interaction.followup.send(f"Queued job #{job_id} for repo {repo}", ephemeral=True)

    @app_commands.command(name="queue_github_org", description="Queue all repos in a GitHub org for indexing")
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
    async def queue_github_org(
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
                    "exts": _split_list(exts),
                    "branch": branch,
                }
            ],
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        job_id = self.bot.services.job_store.enqueue("ingest", payload)  # type: ignore[attr-defined]
        await interaction.followup.send(f"Queued job #{job_id} for org {org}", ephemeral=True)

    @app_commands.command(name="queue_local_dir", description="Queue a local directory for indexing")
    @app_commands.describe(
        repo_root="Local path to repository root on the indexer host",
        repo_url="Public URL used for source links",
        exts="Comma-separated file extensions",
        chunk_size="Optional chunk size",
        chunk_overlap="Optional chunk overlap",
    )
    async def queue_local_dir(
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
                    "exts": _split_list(exts),
                }
            ],
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        job_id = self.bot.services.job_store.enqueue("ingest", payload)  # type: ignore[attr-defined]
        await interaction.followup.send(f"Queued job #{job_id} for path {repo_root}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(IndexQueueCog(bot))

