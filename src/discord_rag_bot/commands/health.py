from __future__ import annotations

import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, MetaData, Table
from rag_core.orm.session import create_engine_from_db

from ..config import settings
from ..util.text import clip_discord_message


def _admin_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        if isinstance(interaction.user, discord.Member):
            return interaction.user.guild_permissions.administrator
        return False
    return app_commands.check(predicate)


class HealthCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="health", description="Show bot/RAG health and configuration")
    @_admin_check()
    async def health(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Basic config
        table = settings.table_name
        expected_dim = settings.embed_dim
        provider = getattr(self.bot.services.rag, "ai_provider", None)  # type: ignore[attr-defined]
        provider_name = provider.__class__.__name__ if provider else "(none)"
        provider_cfg = getattr(provider, "config", None)
        llm_model = getattr(provider_cfg, "llm_model", None)
        emb_model = getattr(provider_cfg, "embedding_model", None)
        emb_backend = getattr(provider_cfg, "embed_backend", None)
        intents_mci = getattr(settings, "enable_message_content_intent", False)

        # DB checks
        eng = create_engine_from_db(settings.db)
        actual_dim: Optional[int] = None
        row_count: Optional[int] = None
        table_name = f"data_{table}"
        try:
            with eng.connect() as conn:
                md = MetaData()
                try:
                    tbl = Table(table_name, md, autoload_with=eng, schema="public")
                except Exception:
                    tbl = None  # type: ignore[assignment]
                if tbl is not None:
                    # Try to infer embedding dimension from reflected column type (pgvector)
                    try:
                        col = tbl.c.embedding  # type: ignore[attr-defined]
                        actual_dim = getattr(col.type, "dim", None)
                        if actual_dim is not None:
                            actual_dim = int(actual_dim)
                    except Exception:
                        actual_dim = None
                    # Count rows
                    try:
                        row_count = int(conn.execute(select(func.count()).select_from(tbl)).scalar() or 0)
                    except Exception:
                        row_count = None
        except Exception:
            # ignore DB errors here; we just present what we have
            pass

        lines = [
            "status: ok",
            f"table: {table}",
            f"embed_dim: expected={expected_dim} actual={actual_dim if actual_dim is not None else '(n/a)'}",
            f"rows: {row_count if row_count is not None else '(unknown)'}",
            f"provider: {provider_name}",
            f"llm_model: {llm_model}",
            f"embedding_model: {emb_model} (backend={emb_backend})",
            f"message_content_intent: {bool(intents_mci)}",
        ]

        # warn on mismatch
        if actual_dim is not None and actual_dim != expected_dim:
            lines[0] = "status: warning"
            lines.append("note: embedding dimension mismatch; consider new table or reindex")

        await interaction.followup.send(clip_discord_message("\n".join(lines)), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HealthCog(bot))
