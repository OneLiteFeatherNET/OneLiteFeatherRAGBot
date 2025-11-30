from __future__ import annotations

import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import create_engine, text

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
        dsn = (
            f"postgresql+psycopg2://{settings.db.user}:{settings.db.password}"
            f"@{settings.db.host}:{settings.db.port}/{settings.db.database}"
        )
        actual_dim: Optional[int] = None
        row_count: Optional[int] = None
        table_name = f"data_{table}"
        try:
            engine = create_engine(dsn, pool_pre_ping=True)
            with engine.connect() as conn:
                # Check table dims
                dim_sql = text(
                    """
                    SELECT (a.atttypmod - 4) / 4 AS dims
                    FROM pg_attribute a
                    JOIN pg_class c ON a.attrelid = c.oid
                    JOIN pg_namespace n ON c.relnamespace = n.oid
                    WHERE n.nspname = 'public' AND c.relname = :table AND a.attname = 'embedding'
                    """
                )
                row = conn.execute(dim_sql, {"table": table_name}).fetchone()
                if row and row[0] is not None:
                    actual_dim = int(row[0])
                # Count rows if table exists
                if actual_dim is not None:
                    cnt_sql = text(f"SELECT COUNT(*) FROM public.{table_name}")
                    row_count = int(conn.execute(cnt_sql).scalar() or 0)
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

