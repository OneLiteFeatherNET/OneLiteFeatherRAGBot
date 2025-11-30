from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import discord

from ..config import settings


Target = Literal["reply", "channel", "thread"]


@dataclass
class ResponsePolicy:
    target: Target
    mention_user: bool
    use_placeholder: bool
    thread_name: str | None = None


def _shorten(text: str, max_len: int = 60) -> str:
    t = (text or "").strip().replace("\n", " ")
    return (t[: max_len - 1] + "…") if len(t) > max_len else t


def decide_response_policy(
    *,
    message: discord.Message,
    question: str,
    is_reply_to_bot: bool,
    expecting_rag: bool,
    user_is_admin: bool,
) -> ResponsePolicy:
    # Default baseline
    target: Target = "reply" if settings.policy_reply_prefer_reply else "channel"
    thread_name: str | None = None

    # Decide mention policy
    mention_mode = (settings.policy_reply_mention or "auto").lower()
    mention_user = False
    if mention_mode == "always":
        mention_user = True
    elif mention_mode == "auto":
        # In replies we usually don't need explicit mention; in channel sends we might if the channel is busy.
        if not is_reply_to_bot and target == "channel":
            mention_user = False

    # Thread heuristic
    if settings.policy_thread_enable and isinstance(message.channel, (discord.TextChannel, discord.Thread)):
        long_question = len(question or "") >= int(settings.policy_thread_min_chars)
        if long_question or (settings.policy_thread_when_sources and expecting_rag):
            # Prefer thread for longer context or when RAG likely (sources)
            target = "thread"
            thread_name = (settings.policy_thread_name_template or "{short_question}").format(
                short_question=_shorten(question)
            )

    use_placeholder = bool(settings.policy_use_placeholder)
    return ResponsePolicy(target=target, mention_user=mention_user, use_placeholder=use_placeholder, thread_name=thread_name)

