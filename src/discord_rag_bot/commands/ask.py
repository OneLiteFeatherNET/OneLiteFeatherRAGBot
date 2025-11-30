from __future__ import annotations

import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from rag_core import RagResult
from ..util.text import clip_discord_message
from ..infrastructure.config_store import load_prompt_effective


class AskCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ask", description="Ask OneLiteFeather code/docs (RAG via pgvector).")
    @app_commands.describe(question="Your question")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer(thinking=True)

        def run_query() -> RagResult:
            prompt = load_prompt_effective(interaction.guild_id, interaction.channel_id)
            return self.bot.services.rag.query(question, system_prompt=prompt)  # type: ignore[attr-defined]

        result = await asyncio.to_thread(run_query)
        text = result.answer
        if result.sources:
            text += "\n\nSources:\n" + "\n".join(f"- {s}" for s in result.sources)

        await interaction.followup.send(clip_discord_message(text))

    # App commands defined in Cogs are automatically registered by discord.py
    # during cog injection; no manual add/remove needed here.


async def setup(bot: commands.Bot):
    await bot.add_cog(AskCog(bot))
