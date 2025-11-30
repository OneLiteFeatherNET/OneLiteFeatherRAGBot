from __future__ import annotations

import asyncio
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

from rag_core.ingestion.github import GitRepoSource
from rag_core.ingestion.filesystem import FilesystemSource

from ..config import settings


def _split_list(csv: Optional[str]) -> Optional[List[str]]:
    if not csv:
        return None
    return [s.strip() for s in csv.split(",") if s.strip()]


class IndexNowCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def admin_check():
        async def predicate(interaction: discord.Interaction) -> bool:
            if isinstance(interaction.user, discord.Member):
                return interaction.user.guild_permissions.administrator
            return False
        return app_commands.check(predicate)

    group = app_commands.Group(name="index", description="Immediately index content (admin)")

    @group.command(name="github_repo", description="Index a GitHub repository now (admin)")
    @admin_check.__func__()
    @app_commands.describe(repo="GitHub repo URL", branch="Optional branch", exts="Comma-separated extensions", force="Reindex even unchanged content")
    async def github_repo(
        self,
        interaction: discord.Interaction,
        repo: str,
        branch: Optional[str] = None,
        exts: Optional[str] = None,
        force: bool = False,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        exts_list = _split_list(exts) or settings.ingest_exts

        def run():
            source = GitRepoSource(repo_url=repo, branch=branch, exts=exts_list)
            self.bot.services.rag.index_items(source.stream(), force=force)  # type: ignore[attr-defined]

        await asyncio.to_thread(run)
        await interaction.followup.send(f"Indexing completed for {repo} (force={force})", ephemeral=True)

    @group.command(name="local_dir", description="Index a local directory now (admin)")
    @admin_check.__func__()
    @app_commands.describe(repo_root="Local path on indexer host", repo_url="Public URL for source links", exts="Comma-separated extensions", force="Reindex even unchanged content")
    async def local_dir(
        self,
        interaction: discord.Interaction,
        repo_root: str,
        repo_url: str,
        exts: Optional[str] = None,
        force: bool = False,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        exts_list = _split_list(exts) or settings.ingest_exts

        def run():
            source = FilesystemSource(repo_root=__import__("pathlib").Path(repo_root), repo_url=repo_url, exts=exts_list)
            self.bot.services.rag.index_items(source.stream(), force=force)  # type: ignore[attr-defined]

        await asyncio.to_thread(run)
        await interaction.followup.send(f"Indexing completed for {repo_root} (force={force})", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(IndexNowCog(bot))

