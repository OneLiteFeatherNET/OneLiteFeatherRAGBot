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
from ..infrastructure.tool_invocation import extract_tool_call, can_run_tools_for_user
from ..infrastructure.tool_planner import maybe_execute_tool_from_text
from ..infrastructure.credits import estimate_credits_for_question, pre_authorize, adjust_usage, compute_user_policy
from ..infrastructure.permissions import is_admin_member
from ..infrastructure.response_policy import decide_response_policy


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
                from ..config import settings as _settings
                ctx_label = getattr(_settings, "reply_context_label", None) or ""
                if ctx_label:
                    question = f"{user_text}\n\n{ctx_label}\n{ref_text}"
                else:
                    question = f"{user_text}\n\n{ref_text}"
            elif user_text:
                question = user_text
            else:
                question = ref_text
        else:
            question = user_text

        if not question:
            # nothing to ask
            return

        # Before answering, let the LLM decide if a tool should be triggered (admin-only)
        try:
            handled = await maybe_execute_tool_from_text(self.bot, message, question)
            if handled:
                return
        except Exception:
            pass

        def _compose_prompt(base: str | None, mem_summary: str | None, recent: list[tuple[str, str]]) -> str:
            from ..config import settings as _settings
            style = getattr(_settings, "chat_style_append", None) or ""
            mem = ""
            if mem_summary:
                summary_hdr = getattr(_settings, "memory_summary_heading", None) if hasattr(_settings, "memory_summary_heading") else None  # type: ignore[attr-defined]
                if not summary_hdr:
                    summary_hdr = ""
                else:
                    summary_hdr = str(summary_hdr)
                if summary_hdr:
                    mem += f"\n{summary_hdr}\n{mem_summary}\n"
                else:
                    mem += f"\n{mem_summary}\n"
            if recent:
                # Kurzer Kontext aus letzten Beiträgen
                lines = []
                for r, c in recent[-6:]:
                    user_pfx = getattr(_settings, "memory_user_prefix", None) if hasattr(_settings, "memory_user_prefix") else None  # type: ignore[attr-defined]
                    bot_pfx = getattr(_settings, "memory_bot_prefix", None) if hasattr(_settings, "memory_bot_prefix") else None  # type: ignore[attr-defined]
                    user_pfx = user_pfx or "User"
                    bot_pfx = bot_pfx or "Bot"
                    prefix = user_pfx if r == "user" else bot_pfx
                    lines.append(f"- {prefix}: {c[:300]}")
                recent_hdr = getattr(_settings, "memory_recent_heading", None) if hasattr(_settings, "memory_recent_heading") else None  # type: ignore[attr-defined]
                if not recent_hdr:
                    recent_hdr = ""
                else:
                    recent_hdr = str(recent_hdr)
                if recent_hdr:
                    mem += "\n" + recent_hdr + "\n" + "\n".join(lines) + "\n"
                else:
                    mem += "\n" + "\n".join(lines) + "\n"
            base = base or ""
            return (base + ("\n\n" + style if style else "") + mem).strip()

        # Memory channel selection (may switch to thread later)
        mem_channel_id = message.channel.id if hasattr(message.channel, "id") else None

        def run_query() -> tuple[str, list[str]]:
            base_prompt = load_prompt_effective(message.guild.id if message.guild else None, message.channel.id)
            # Load user memory via service (summary + recent channel messages)
            mem = self.bot.services.memory.get_context(user_id=message.author.id, channel_id=mem_channel_id)  # type: ignore[attr-defined]
            prompt = _compose_prompt(base_prompt, mem.summary, mem.recent)
            lang_hint = get_language_hint(question)
            if lang_hint:
                from ..config import settings as _settings
                tmpl = getattr(_settings, "language_hint_template", None)
                if tmpl:
                    try:
                        hint = str(tmpl).format(lang=lang_hint)
                        prompt = f"{prompt}\n\n{hint}"
                    except Exception:
                        pass
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

        # Decide response target and send placeholder
        try:
            pre_expect_rag = should_use_rag(
                question,
                guild_name=message.guild.name if message.guild else None,
                channel_name=message.channel.name if hasattr(message.channel, "name") else None,
                best_score=None,
                sources_count=0,
            )
        except Exception:
            pre_expect_rag = False
        user_is_admin = bool(isinstance(message.author, discord.Member) and message.author.guild_permissions.administrator)
        policy = decide_response_policy(
            message=message,
            question=question,
            is_reply_to_bot=is_reply_to_bot,
            expecting_rag=bool(pre_expect_rag),
            user_is_admin=user_is_admin,
        )
        from ..config import settings as _settings
        placeholder = getattr(_settings, "reply_placeholder_text", None) or "…"
        placeholder_msg: discord.Message
        dest_thread: Optional[discord.Thread] = None
        try:
            if policy.target == "thread":
                try:
                    dest_thread = await message.create_thread(name=policy.thread_name or "Discussion")
                    placeholder_msg = await dest_thread.send(placeholder)
                    # Switch memory channel to thread id
                    mem_channel_id = getattr(dest_thread, "id", None)
                except Exception:
                    placeholder_msg = await message.reply(placeholder, mention_author=policy.mention_user)
            elif policy.target == "channel":
                prefix = f"{message.author.mention} " if policy.mention_user else ""
                placeholder_msg = await message.channel.send(prefix + placeholder)  # type: ignore[union-attr]
            else:
                placeholder_msg = await message.reply(placeholder, mention_author=policy.mention_user)
        except Exception:
            placeholder_msg = await message.reply(placeholder)
        # Credits: pre-authorize based on estimate (if enabled)
        est_credits = 0
        reserved = 0
        user_unlimited = False
        if getattr(self.bot, "services", None) and getattr(self.bot.services, "rag", None):  # basic sanity
            try:
                from ..config import settings as _settings
                if getattr(_settings, "credit_enabled", False):
                    est_credits = estimate_credits_for_question(question)
                    # Resolve user policy (unlimited or per-user limit)
                    roles = []
                    is_admin = False
                    if isinstance(message.author, discord.Member):
                        for r in message.author.roles:
                            roles.append((int(getattr(r, "id", 0) or 0), str(getattr(r, "name", "") or "")))
                        is_admin = bool(is_admin_member(message.author))
                    user_unlimited, user_limit = compute_user_policy(user_id=int(message.author.id), member_roles=roles, is_admin=is_admin)
                    # Pre-authorize in a thread to avoid event-loop blocking
                    ok, _, _ = await asyncio.to_thread(pre_authorize, int(message.author.id), int(est_credits), user_limit_override=int(user_limit))
                    if not ok:
                        no_credit_msg = getattr(_settings, "credits_exhausted_message", None) or "Credits exhausted"
                        await placeholder_msg.edit(content=no_credit_msg)
                        return
                    reserved = est_credits
            except Exception:
                pass
        # Save the incoming user message into memory (best-effort)
        try:
            self.bot.services.memory.record_user_message(  # type: ignore[attr-defined]
                user_id=message.author.id,
                guild_id=message.guild.id if message.guild else None,
                channel_id=mem_channel_id,
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
            hdr = getattr(_settings, "sources_heading", None) or "Sources:"
            text += "\n\n" + hdr + "\n" + "\n".join(f"- {s}" for s in sources)

        try:
            prefix = f"{message.author.mention} " if (policy.mention_user and policy.target == "channel") else ""
            await placeholder_msg.edit(content=clip_discord_message(prefix + text))
        except Exception:
            # Fallback: send a fresh reply if edit fails
            await message.reply(clip_discord_message(text), mention_author=policy.mention_user)

        # Optional: detect and run a tool call embedded in the model answer (fenced JSON)
        try:
            tc = extract_tool_call(text)
            if tc:
                name, payload = tc
                if can_run_tools_for_user(message.author):
                    # run tool in background thread to avoid blocking loop
                    import asyncio as _asyncio
                    async def _run_tool():
                        try:
                            res = await _asyncio.to_thread(self.bot.services.tools.call, name, payload)  # type: ignore[attr-defined]
                            await message.channel.send(f"🛠️ Tool '{name}' → {res.content}")  # type: ignore[union-attr]
                        except Exception as e:
                            await message.channel.send(f"🛠️ Tool '{name}' failed: {e}")  # type: ignore[union-attr]
                    _asyncio.create_task(_run_tool())
                else:
                    await message.channel.send("⛔ You are not allowed to run tools here.")  # type: ignore[union-attr]
        except Exception:
            pass
        # Adjust credits after answer based on actual output length (best-effort)
        try:
            if reserved > 0:
                from ..config import settings as _settings
                if getattr(_settings, "credit_enabled", False):
                    # crude estimate: input + actual output
                    out_tokens = int(len(text or "") * float(getattr(_settings, "credit_tokens_per_char", 0.25)))
                    final = int((int(len(question) * float(_settings.credit_tokens_per_char)) + out_tokens + 999) // 1000 * float(_settings.credit_per_1k_tokens))
                    delta = max(0, int(final) - int(reserved))
                    if delta != 0:
                        await asyncio.to_thread(pre_authorize, int(message.author.id), int(delta))
        except Exception:
            pass
        # Save bot answer and update summary in background (best-effort)
        try:
            self.bot.services.memory.record_assistant_message(  # type: ignore[attr-defined]
                user_id=message.author.id,
                guild_id=message.guild.id if message.guild else None,
                channel_id=mem_channel_id,
                content=text,
            )
        except Exception:
            pass
        # Summarize/update user memory asynchronously
        async def _update_summary_bg():
            try:
                await asyncio.to_thread(
                    self.bot.services.memory.update_summary,  # type: ignore[attr-defined]
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
