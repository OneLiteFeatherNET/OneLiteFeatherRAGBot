from __future__ import annotations

import asyncio
from typing import Optional

import discord
from discord.ext import commands

from ..util.text import clip_discord_message
from rag_core import RagResult
from ..infrastructure.config_store import load_prompt_effective
from ..infrastructure.gating import should_use_rag
from ..infrastructure.language import get_language_hint
from rag_core.metrics import discord_messages_processed_total, rag_queries_total


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
        try:
            discord_messages_processed_total.inc()
        except Exception:
            pass

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

        def _style_prompt(base: str | None, mem_summary: str | None, recent: list[tuple[str, str]]) -> str:
            style = (
                "Du antwortest hilfreich, prägnant und mit trockenem Sarkasmus, ohne unhöflich zu sein.\n"
                "Nutze passende Discord-Emojis (z. B. 😅, 🤔, ✅, ❌, 🧠, 🔧, 📎), aber nicht übermäßig.\n"
                "Wenn Daten fehlen, sag es ehrlich. Antworte in der Sprache des Nutzers.\n"
            )
            mem = ""
            if mem_summary:
                mem += f"\nNutzerprofil (Zusammenfassung):\n{mem_summary}\n"
            if recent:
                # Kurzer Kontext aus letzten Beiträgen
                lines = []
                for r, c in recent[-6:]:
                    prefix = "User" if r == "user" else "Bot"
                    lines.append(f"- {prefix}: {c[:300]}")
                mem += "\nLetzte Unterhaltungsschritte:\n" + "\n".join(lines) + "\n"
            base = base or ""
            return (base + "\n\n" + style + mem).strip()

        def run_query() -> tuple[str, list[str]]:
            base_prompt = load_prompt_effective(message.guild.id if message.guild else None, message.channel.id)
            # Load user memory via service (summary + recent channel messages)
            mem = self.bot.services.memory.get_context(user_id=message.author.id, channel_id=message.channel.id)  # type: ignore[attr-defined]
            prompt = _style_prompt(base_prompt, mem.summary, mem.recent)
            lang_hint = get_language_hint(question)
            if lang_hint:
                prompt = f"{prompt}\n\nAntwortsprache: {lang_hint}"
            # 1) Heuristik: Smalltalk etc. ohne teures Retrieval beantworten
            pre = should_use_rag(
                question,
                guild_name=message.guild.name if message.guild else None,
                channel_name=message.channel.name if hasattr(message.channel, "name") else None,
                best_score=None,
                sources_count=0,
            )
            if not pre:
                ans = self.bot.services.rag.answer_llm(question, system_prompt=prompt)  # type: ignore[attr-defined]
                try:
                    rag_queries_total.labels(mode="llm").inc()
                except Exception:
                    pass
                return ans, []

            # 2) Wenn Heuristik RAG nahelegt: Retrieval ausführen und mit Score entscheiden
            res = self.bot.services.rag.query(question, system_prompt=prompt)  # type: ignore[attr-defined]
            use_rag = should_use_rag(
                question,
                guild_name=message.guild.name if message.guild else None,
                channel_name=message.channel.name if hasattr(message.channel, "name") else None,
                best_score=res.best_score,
                score_kind=res.score_kind,
                sources_count=len(res.sources),
            )
            if use_rag:
                return str(res.answer), res.sources
            else:
                ans = self.bot.services.rag.answer_llm(question, system_prompt=prompt)  # type: ignore[attr-defined]
                try:
                    rag_queries_total.labels(mode="llm").inc()
                except Exception:
                    pass
                return ans, []

        # Send friendly placeholder reply and then edit when ready
        placeholder_msg = await message.reply("🧠 Einen kleinen Moment – ich suche passende Informationen und schreibe die Antwort …")
        # Save the incoming user message into memory (best-effort)
        try:
            self.bot.services.memory.record_user_message(  # type: ignore[attr-defined]
                user_id=message.author.id,
                guild_id=message.guild.id if message.guild else None,
                channel_id=message.channel.id if hasattr(message.channel, "id") else None,
                content=message.content or "",
            )
        except Exception:
            pass
        answer, sources = await asyncio.to_thread(run_query)
        if sources:
            try:
                rag_queries_total.labels(mode="rag").inc()
            except Exception:
                pass
        text = answer
        if sources:
            text += "\n\nSources:\n" + "\n".join(f"- {s}" for s in sources)

        try:
            await placeholder_msg.edit(content=clip_discord_message(text))
        except Exception:
            # Fallback: send a fresh reply if edit fails
            await message.reply(clip_discord_message(text))
        # Save bot answer and update summary in background (best-effort)
        try:
            self.bot.services.memory.record_assistant_message(  # type: ignore[attr-defined]
                user_id=message.author.id,
                guild_id=message.guild.id if message.guild else None,
                channel_id=message.channel.id if hasattr(message.channel, "id") else None,
                content=text,
            )
        except Exception:
            pass
        # Summarize/update user memory asynchronously
        async def _update_summary_bg():
            try:
                self.bot.services.memory.update_summary(  # type: ignore[attr-defined]
                    user_id=message.author.id,
                    user_text=message.content or "",
                    bot_answer=text,
                    answer_llm=lambda q, system_prompt: self.bot.services.rag.answer_llm(q, system_prompt=system_prompt),  # type: ignore[attr-defined]
                )
            except Exception:
                pass

        try:
            asyncio.create_task(_update_summary_bg())
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatListenerCog(bot))
