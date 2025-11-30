from __future__ import annotations

import asyncio
from typing import Optional

import discord
from discord.ext import commands

from ..util.text import clip_discord_message
from rag_core import RagResult


class ChatListenerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_allowed_guild(self, guild: Optional[discord.Guild]) -> bool:
        allowed = getattr(self.bot, "_allowed_guild_ids", set())  # type: ignore[attr-defined]
        if not allowed or guild is None:
            return True
        return guild.id in allowed

    def _strip_bot_mention(self, content: str) -> str:
        if not self.bot.user:
            return content
        mention_vars = [
            self.bot.user.mention,
            f"<@{self.bot.user.id}>",
            f"<@!{self.bot.user.id}>",
        ]
        out = content
        for m in mention_vars:
            out = out.replace(m, "")
        return out.strip()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore self and other bots
        if message.author.bot:
            return
        if not self._is_allowed_guild(message.guild):
            return
        if not self.bot.user:
            return

        is_mention = self.bot.user in message.mentions
        is_reply_to_bot = False
        if message.reference and isinstance(message.reference.resolved, discord.Message):
            ref_msg: discord.Message = message.reference.resolved
            is_reply_to_bot = ref_msg.author.id == self.bot.user.id

        if not (is_mention or is_reply_to_bot):
            return

        # Build question by removing bot mention
        question = self._strip_bot_mention(message.content or "")
        if not question:
            # If user replied to bot without text, do nothing
            return

        await message.channel.typing().__aenter__()

        def run_query() -> RagResult:
            return self.bot.services.rag.query(question)  # type: ignore[attr-defined]

        try:
            result = await asyncio.to_thread(run_query)
        finally:
            await message.channel.typing().__aexit__(None, None, None)

        text = result.answer
        if result.sources:
            text += "\n\nSources:\n" + "\n".join(f"- {s}" for s in result.sources)

        await message.reply(clip_discord_message(text))


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatListenerCog(bot))

