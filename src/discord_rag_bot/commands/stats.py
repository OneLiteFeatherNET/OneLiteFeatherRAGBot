from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, MetaData, Table
from sqlalchemy.dialects.postgresql import JSONB
from rag_core.orm.session import create_engine_from_db

from ..config import settings
from ..util.text import clip_discord_message
from ..infrastructure.permissions import require_admin


class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    stats = app_commands.Group(name="stats", description="Administrative statistics")

    @stats.command(name="rag_size", description="Zeigt Umfang des Wissens (Chunks, Dokumente, Größe) aus der Datenbank")
    @require_admin()
    async def rag_size(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        table = settings.table_name
        table_name = f"data_{table}"
        embed_dim = int(settings.embed_dim)

        eng = create_engine_from_db(settings.db)

        total_chunks: Optional[int] = None
        total_chars: Optional[int] = None
        distinct_docs: Optional[int] = None
        actual_dim: Optional[int] = None

        try:
            with eng.connect() as conn:
                md = MetaData()
                try:
                    tbl = Table(table_name, md, autoload_with=eng, schema="public")
                except Exception:
                    tbl = None  # type: ignore[assignment]
                if tbl is not None:
                    # Dimension from reflected pgvector column
                    try:
                        col = tbl.c.embedding  # type: ignore[attr-defined]
                        actual_dim = getattr(col.type, "dim", None)
                        if actual_dim is not None:
                            actual_dim = int(actual_dim)
                    except Exception:
                        actual_dim = None

                    total_chunks = int(conn.execute(select(func.count()).select_from(tbl)).scalar() or 0)
                    total_chars = int(conn.execute(select(func.sum(func.octet_length(tbl.c.text)))).scalar() or 0)

                    # Distinct docs: COALESCE(jsonb_extract_path_text(metadata_, 'parent_id'), ... , node_id)
                    metadata_col = func.cast(tbl.c.metadata_, JSONB)
                    parent = func.jsonb_extract_path_text(metadata_col, "parent_id")
                    refdoc = func.jsonb_extract_path_text(metadata_col, "ref_doc_id")
                    doc_expr = func.coalesce(parent, refdoc, tbl.c.node_id)
                    distinct_docs = int(conn.execute(select(func.count(func.distinct(doc_expr)))).scalar() or 0)
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
