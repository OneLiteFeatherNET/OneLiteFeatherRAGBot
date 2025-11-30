from __future__ import annotations

import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from rag_core import RagResult
from ..util.text import clip_discord_message
from ..infrastructure.config_store import load_prompt_effective
from ..infrastructure.gating import should_use_rag


class AskCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ask", description="Ask OneLiteFeather code/docs (RAG via pgvector).")
    @app_commands.describe(question="Your question")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer(thinking=True)
        # Show a friendly placeholder immediately, then edit when finished
        placeholder = "🧠 Einen kleinen Moment – ich suche passende Informationen und schreibe die Antwort …"
        try:
            await interaction.edit_original_response(content=placeholder)
        except Exception:
            pass

        def run_query() -> tuple[str, list[str]]:
            prompt = load_prompt_effective(interaction.guild_id, interaction.channel_id)
            # 1) Lightweight Gating ohne Retrieval (Smalltalk etc.)
            pre = should_use_rag(
                question,
                guild_name=interaction.guild.name if interaction.guild else None,
                channel_name=interaction.channel.name if hasattr(interaction.channel, "name") else None,
                best_score=None,
                sources_count=0,
            )
            if not pre:
                ans = self.bot.services.rag.answer_llm(question, system_prompt=prompt)  # type: ignore[attr-defined]
                return ans, []

            # 2) Retrieval + Score‑basiertes Gating
            res = self.bot.services.rag.query(question, system_prompt=prompt)  # type: ignore[attr-defined]
            use_rag = should_use_rag(
                question,
                guild_name=interaction.guild.name if interaction.guild else None,
                channel_name=interaction.channel.name if hasattr(interaction.channel, "name") else None,
                best_score=res.best_score,
                score_kind=res.score_kind,
                sources_count=len(res.sources),
            )
            if use_rag:
                return str(res.answer), res.sources
            else:
                ans = self.bot.services.rag.answer_llm(question, system_prompt=prompt)  # type: ignore[attr-defined]
                return ans, []

        answer, sources = await asyncio.to_thread(run_query)
        text = answer
        if sources:
            text += "\n\nSources:\n" + "\n".join(f"- {s}" for s in sources)

        await interaction.edit_original_response(content=clip_discord_message(text))

    # App commands defined in Cogs are automatically registered by discord.py
    # during cog injection; no manual add/remove needed here.


async def setup(bot: commands.Bot):
    await bot.add_cog(AskCog(bot))
