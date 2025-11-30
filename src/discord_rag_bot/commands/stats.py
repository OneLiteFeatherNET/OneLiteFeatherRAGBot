from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import create_engine, text

from ..config import settings
from ..util.text import clip_discord_message


class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    stats = app_commands.Group(name="stats", description="Administrative statistics")

    @staticmethod
    def admin_check():
        async def predicate(interaction: discord.Interaction) -> bool:
            if isinstance(interaction.user, discord.Member):
                return interaction.user.guild_permissions.administrator
            return False
        return app_commands.check(predicate)

    @stats.command(name="rag_size", description="Zeigt Umfang des Wissens (Chunks, Dokumente, Größe) aus der Datenbank")
    @admin_check.__func__()
    async def rag_size(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        table = settings.table_name
        table_name = f"data_{table}"
        embed_dim = int(settings.embed_dim)

        dsn = (
            f"postgresql+psycopg2://{settings.db.user}:{settings.db.password}"
            f"@{settings.db.host}:{settings.db.port}/{settings.db.database}"
        )

        total_chunks: Optional[int] = None
        total_chars: Optional[int] = None
        distinct_docs: Optional[int] = None
        actual_dim: Optional[int] = None

        try:
            engine = create_engine(dsn, pool_pre_ping=True)
            with engine.connect() as conn:
                # Verify table and dimension
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

                # Counts
                cnt_sql = text(f"SELECT COUNT(*) FROM public.{table_name}")
                total_chunks = int(conn.execute(cnt_sql).scalar() or 0)

                char_sql = text(f"SELECT SUM(OCTET_LENGTH(text)) FROM public.{table_name}")
                total_chars = int(conn.execute(char_sql).scalar() or 0)

                # Distinct documents: prefer parent_id, then ref_doc_id, else node_id
                docs_sql = text(
                    f"""
                    SELECT COUNT(DISTINCT COALESCE(metadata_->>'parent_id', metadata_->>'ref_doc_id', node_id))
                    FROM public.{table_name}
                    """
                )
                distinct_docs = int(conn.execute(docs_sql).scalar() or 0)
        except Exception as e:
            await interaction.followup.send(f"Fehler beim Lesen der Statistiken: {e}", ephemeral=True)
            return

        # Approximations
        # Text size in MB
        text_mb = (total_chars or 0) / (1024 * 1024)
        # Vector size: float4 per dimension
        vec_bytes_total = (total_chunks or 0) * embed_dim * 4
        vec_mb = vec_bytes_total / (1024 * 1024)

        lines = [
            f"Tabelle: {table_name}",
            f"Embedding-Dimension: erwartet={embed_dim} aktuell={(actual_dim if actual_dim is not None else '(n/a)')}",
            f"Chunks: {total_chunks if total_chunks is not None else '(n/a)'}",
            f"Ungefähre Textgröße: {text_mb:.2f} MiB",
            f"Ungefähre Vektordaten: {vec_mb:.2f} MiB",
            f"Geschätzte Dokumente (distinct): {distinct_docs if distinct_docs is not None else '(n/a)'}",
        ]

        # Warnung bei Dimensions-Mismatch
        if actual_dim is not None and actual_dim != embed_dim:
            lines.append("Hinweis: Embedding-Dimension weicht ab – ggf. Tabelle wechseln oder reindizieren.")

        await interaction.followup.send(clip_discord_message("\n".join(lines)), ephemeral=True)


async def setup(bot: commands.Bot):
    cog = StatsCog(bot)
    await bot.add_cog(cog)
    try:
        bot.tree.add_command(StatsCog.stats)
    except Exception:
        pass
