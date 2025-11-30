from __future__ import annotations

import asyncio
from typing import Optional

import discord
from discord.ext import commands

from ..util.text import clip_discord_message
from rag_core import RagResult
from ..infrastructure/config_store import load_prompt_effective


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
        ref_msg: Optional[discord.Message] = None
        if message.reference and isinstance(message.reference.resolved, discord.Message):
            ref_msg = message.reference.resolved
            is_reply_to_bot = ref_msg.author.id == self.bot.user.id

        if not (is_mention or is_reply_to_bot):
            return

        # Build question by removing bot mention
        user_text = self._strip_bot_mention(message.content or "")

        # For replies to the bot, allow mixing prior bot message as context
        if is_reply_to_bot:
            ref_text = (ref_msg.content or "").strip() if ref_msg else ""
            if user_text and ref_text:
                question = f"{user_text}\n\nContext (previous bot message):\n{ref_text}"
            elif user_text:
                question = user_text
            else:
                question = ref_text
        else:
            question = user_text

        if not question:
            # nothing to ask
            return

        def run_query() -> RagResult:
            prompt = load_prompt_effective(message.guild.id if message.guild else None, message.channel.id)
            return self.bot.services.rag.query(question, system_prompt=prompt)  # type: ignore[attr-defined]

        # Send friendly placeholder reply and then edit when ready
        placeholder_msg = await message.reply("🧠 Einen kleinen Moment – ich suche passende Informationen und schreibe die Antwort …")
        result = await asyncio.to_thread(run_query)

        text = result.answer
        if result.sources:
            text += "\n\nSources:\n" + "\n".join(f"- {s}" for s in result.sources)

        try:
            await placeholder_msg.edit(content=clip_discord_message(text))
        except Exception:
            # Fallback: send a fresh reply if edit fails
            await message.reply(clip_discord_message(text))


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatListenerCog(bot))
