from __future__ import annotations

import asyncio
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

from rag_core.ingestion.github import GitRepoSource
from rag_core.ingestion.filesystem import FilesystemSource
from rag_core.ingestion.web import UrlSource, WebsiteCrawlerSource

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
        loop = asyncio.get_running_loop()

        def run():
            source = GitRepoSource(repo_url=repo, branch=branch, exts=exts_list)

            def progress(stage: str, *, done: int | None = None, total: int | None = None, note: str | None = None):
                content = f"Indexing {repo}: {stage}"
                if total is not None or done is not None:
                    content += f" ({done or 0}/{total or '?'})"
                if note:
                    content += f" – {note}"
                try:
                    asyncio.run_coroutine_threadsafe(
                        interaction.edit_original_response(content=content), loop
                    )
                except Exception:
                    pass

            self.bot.services.rag.index_items(source.stream(), force=force, progress=progress)  # type: ignore[attr-defined]

        await asyncio.to_thread(run)
        await interaction.edit_original_response(content=f"Indexing completed for {repo} (force={force})")

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
        loop = asyncio.get_running_loop()

        def run():
            source = FilesystemSource(repo_root=__import__("pathlib").Path(repo_root), repo_url=repo_url, exts=exts_list)

            def progress(stage: str, *, done: int | None = None, total: int | None = None, note: str | None = None):
                content = f"Indexing {repo_root}: {stage}"
                if total is not None or done is not None:
                    content += f" ({done or 0}/{total or '?'})"
                if note:
                    content += f" – {note}"
                try:
                    asyncio.run_coroutine_threadsafe(
                        interaction.edit_original_response(content=content), loop
                    )
                except Exception:
                    pass

            self.bot.services.rag.index_items(source.stream(), force=force, progress=progress)  # type: ignore[attr-defined]

        await asyncio.to_thread(run)
        await interaction.edit_original_response(content=f"Indexing completed for {repo_root} (force={force})")

    @group.command(name="web_url", description="Index specific web URLs now (admin)")
    @admin_check.__func__()
    @app_commands.describe(urls="Comma-separated list of URLs", force="Reindex even unchanged content")
    async def web_url(self, interaction: discord.Interaction, urls: str, force: bool = False):
        await interaction.response.defer(ephemeral=True, thinking=True)
        loop = asyncio.get_running_loop()
        url_list = [u.strip() for u in urls.split(",") if u.strip()]

        def run():
            source = UrlSource(urls=url_list)

            def progress(stage: str, *, done: int | None = None, total: int | None = None, note: str | None = None):
                content = f"Indexing URLs: {stage} ({done or 0}/{total or '?'})"
                try:
                    asyncio.run_coroutine_threadsafe(
                        interaction.edit_original_response(content=content), loop
                    )
                except Exception:
                    pass

            self.bot.services.rag.index_items(source.stream(), force=force, progress=progress)  # type: ignore[attr-defined]

        await asyncio.to_thread(run)
        await interaction.edit_original_response(content=f"Indexing completed for {len(url_list)} URLs (force={force})")

    @group.command(name="website", description="Crawl and index a website section now (admin)")
    @admin_check.__func__()
    @app_commands.describe(start_url="Start URL (seed)", allowed_prefixes="Comma-separated URL prefixes to keep within", max_pages="Max pages to crawl", force="Reindex even unchanged content")
    async def website(self, interaction: discord.Interaction, start_url: str, allowed_prefixes: str = "", max_pages: int = 200, force: bool = False):
        await interaction.response.defer(ephemeral=True, thinking=True)
        loop = asyncio.get_running_loop()
        prefixes = [p.strip() for p in allowed_prefixes.split(",") if p.strip()] or [start_url]

        def run():
            source = WebsiteCrawlerSource(start_urls=[start_url], allowed_prefixes=prefixes, max_pages=max_pages)

            def progress(stage: str, *, done: int | None = None, total: int | None = None, note: str | None = None):
                content = f"Crawling {start_url}: {stage} ({done or 0}/{total or '?'})"
                try:
                    asyncio.run_coroutine_threadsafe(
                        interaction.edit_original_response(content=content), loop
                    )
                except Exception:
                    pass

            self.bot.services.rag.index_items(source.stream(), force=force, progress=progress)  # type: ignore[attr-defined]

        await asyncio.to_thread(run)
        await interaction.edit_original_response(content=f"Website crawl completed (force={force})")


async def setup(bot: commands.Bot):
    await bot.add_cog(IndexNowCog(bot))
