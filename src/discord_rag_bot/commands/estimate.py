from __future__ import annotations

import asyncio
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

from pathlib import Path

from ..config import settings
from ..util.text import clip_discord_message
from rag_core.ingestion.github import GitRepoSource, GitHubOrgSource
from rag_core.ingestion.github import GitHubIssuesSource
from rag_core.ingestion.filesystem import FilesystemSource
from rag_core.ingestion.web import UrlSource, WebsiteCrawlerSource, SitemapSource
from rag_core.ingestion.chunked import ChunkingSource


def _split_list(csv: Optional[str]) -> Optional[List[str]]:
    if not csv:
        return None
    return [s.strip() for s in csv.split(",") if s.strip()]


def _human_duration(seconds: float) -> str:
    s = int(round(max(0.0, seconds)))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


class EstimateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="estimate", description="Geschätzte Dauer für Indizierung (admin)")

    @staticmethod
    def admin_check():
        async def predicate(interaction: discord.Interaction) -> bool:
            if isinstance(interaction.user, discord.Member):
                return interaction.user.guild_permissions.administrator
            return False
        return app_commands.check(predicate)

    def _estimate_for_source(self, source) -> tuple[int, int, float]:
        # returns (chunks, total_chars, seconds_estimate)
        ex_tps = float(getattr(settings, "estimate_tokens_per_sec", 2500.0))
        ex_wps = float(getattr(settings, "estimate_db_writes_per_sec", 200.0))
        overhead = float(getattr(settings, "estimate_overhead_sec", 5.0))

        count = 0
        chars = 0
        for it in source.stream():
            count += 1
            chars += len(it.text or "")
        tokens = chars / 4.0
        embed_sec = tokens / ex_tps if ex_tps > 0 else 0.0
        db_sec = count / ex_wps if ex_wps > 0 else 0.0
        total = overhead + embed_sec + db_sec
        return count, chars, total

    # GitHub repo
    @group.command(name="github_repo", description="Schätzt die Dauer für ein GitHub-Repository")
    @admin_check.__func__()
    @app_commands.describe(repo="GitHub repo URL", branch="Optionaler Branch", exts="Kommagetrennte Endungen", chunk_size="Chunkgröße", chunk_overlap="Overlap")
    async def estimate_github_repo(self, interaction: discord.Interaction, repo: str, branch: Optional[str] = None, exts: Optional[str] = None, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = 200):
        await interaction.response.defer(ephemeral=True)
        exts_list = _split_list(exts) or settings.ingest_exts
        src: object = GitRepoSource(repo_url=repo, branch=branch, exts=exts_list)
        if chunk_size:
            src = ChunkingSource(source=src, chunk_size=chunk_size or 0, overlap=chunk_overlap or 200)  # type: ignore[arg-type]
        chunks, chars, secs = await asyncio.to_thread(self._estimate_for_source, src)
        await interaction.followup.send(clip_discord_message(f"Repo: {repo}\nChunks: {chunks}\nText: {chars} Zeichen (~{int(chars/4)} Tokens)\nSchätzung: {_human_duration(secs)}"), ephemeral=True)

    # Local dir
    @group.command(name="local_dir", description="Schätzt die Dauer für ein lokales Verzeichnis")
    @admin_check.__func__()
    @app_commands.describe(repo_root="Lokaler Pfad", repo_url="Öffentliche URL", exts="Kommagetrennte Endungen", chunk_size="Chunkgröße", chunk_overlap="Overlap")
    async def estimate_local_dir(self, interaction: discord.Interaction, repo_root: str, repo_url: str, exts: Optional[str] = None, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = 200):
        await interaction.response.defer(ephemeral=True)
        exts_list = _split_list(exts) or settings.ingest_exts
        src: object = FilesystemSource(repo_root=Path(repo_root), repo_url=repo_url, exts=exts_list)
        if chunk_size:
            src = ChunkingSource(source=src, chunk_size=chunk_size or 0, overlap=chunk_overlap or 200)  # type: ignore[arg-type]
        chunks, chars, secs = await asyncio.to_thread(self._estimate_for_source, src)
        await interaction.followup.send(clip_discord_message(f"Pfad: {repo_root}\nChunks: {chunks}\nText: {chars} Zeichen (~{int(chars/4)} Tokens)\nSchätzung: {_human_duration(secs)}"), ephemeral=True)

    # GitHub Issues
    @group.command(name="github_issues", description="Schätzt die Dauer für GitHub-Issues eines Repos")
    @admin_check.__func__()
    @app_commands.describe(repo="GitHub repo URL", state="all|open|closed", labels="Labels", include_comments="Kommentare einbeziehen", chunk_size="Chunkgröße", chunk_overlap="Overlap")
    async def estimate_github_issues(self, interaction: discord.Interaction, repo: str, state: str = "all", labels: Optional[str] = None, include_comments: bool = True, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = 200):
        await interaction.response.defer(ephemeral=True)
        src: object = GitHubIssuesSource(repo_url=repo, state=state, labels=_split_list(labels), include_comments=include_comments)
        if chunk_size:
            src = ChunkingSource(source=src, chunk_size=chunk_size or 0, overlap=chunk_overlap or 200)  # type: ignore[arg-type]
        chunks, chars, secs = await asyncio.to_thread(self._estimate_for_source, src)
        await interaction.followup.send(clip_discord_message(f"Issues: {repo}\nChunks: {chunks}\nText: {chars} Zeichen (~{int(chars/4)} Tokens)\nSchätzung: {_human_duration(secs)}"), ephemeral=True)

    # Web URLs
    @group.command(name="web_url", description="Schätzt die Dauer für konkrete URLs")
    @admin_check.__func__()
    @app_commands.describe(urls="Kommagetrennte Liste von URLs", chunk_size="Chunkgröße", chunk_overlap="Overlap")
    async def estimate_web_url(self, interaction: discord.Interaction, urls: str, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = 200):
        await interaction.response.defer(ephemeral=True)
        url_list = [u.strip() for u in urls.split(",") if u.strip()]
        src: object = UrlSource(urls=url_list)
        if chunk_size:
            src = ChunkingSource(source=src, chunk_size=chunk_size or 0, overlap=chunk_overlap or 200)  # type: ignore[arg-type]
        chunks, chars, secs = await asyncio.to_thread(self._estimate_for_source, src)
        await interaction.followup.send(clip_discord_message(f"URLs: {len(url_list)}\nChunks: {chunks}\nText: {chars} Zeichen (~{int(chars/4)} Tokens)\nSchätzung: {_human_duration(secs)}"), ephemeral=True)

    # Website crawler
    @group.command(name="website", description="Schätzt die Dauer für eine Website-Crawl")
    @admin_check.__func__()
    @app_commands.describe(start_url="Start-URL", allowed_prefixes="Kommagetrennte Präfixe", max_pages="Max Seiten", chunk_size="Chunkgröße", chunk_overlap="Overlap")
    async def estimate_website(self, interaction: discord.Interaction, start_url: str, allowed_prefixes: str = "", max_pages: int = 200, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = 200):
        await interaction.response.defer(ephemeral=True)
        prefixes = [p.strip() for p in allowed_prefixes.split(",") if p.strip()] or [start_url]
        src: object = WebsiteCrawlerSource(start_urls=[start_url], allowed_prefixes=prefixes, max_pages=max_pages)
        if chunk_size:
            src = ChunkingSource(source=src, chunk_size=chunk_size or 0, overlap=chunk_overlap or 200)  # type: ignore[arg-type]
        chunks, chars, secs = await asyncio.to_thread(self._estimate_for_source, src)
        await interaction.followup.send(clip_discord_message(f"Crawl: {start_url} (max {max_pages} Seiten)\nChunks: {chunks}\nText: {chars} Zeichen (~{int(chars/4)} Tokens)\nSchätzung: {_human_duration(secs)}"), ephemeral=True)

    # Sitemap
    @group.command(name="sitemap", description="Schätzt die Dauer für eine Sitemap")
    @admin_check.__func__()
    @app_commands.describe(sitemap_url="Sitemap URL", limit="Limit" , chunk_size="Chunkgröße", chunk_overlap="Overlap")
    async def estimate_sitemap(self, interaction: discord.Interaction, sitemap_url: str, limit: Optional[int] = None, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = 200):
        await interaction.response.defer(ephemeral=True)
        src: object = SitemapSource(sitemap_url=sitemap_url, limit=limit)
        if chunk_size:
            src = ChunkingSource(source=src, chunk_size=chunk_size or 0, overlap=chunk_overlap or 200)  # type: ignore[arg-type]
        chunks, chars, secs = await asyncio.to_thread(self._estimate_for_source, src)
        await interaction.followup.send(clip_discord_message(f"Sitemap: {sitemap_url}\nChunks: {chunks}\nText: {chars} Zeichen (~{int(chars/4)} Tokens)\nSchätzung: {_human_duration(secs)}"), ephemeral=True)


async def setup(bot: commands.Bot):
    cog = EstimateCog(bot)
    await bot.add_cog(cog)
    try:
        bot.tree.add_command(EstimateCog.group)
    except Exception:
        pass
