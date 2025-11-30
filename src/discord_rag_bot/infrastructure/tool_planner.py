from __future__ import annotations

from typing import Optional, Tuple, Dict, Any

from .tool_invocation import extract_tool_call, can_run_tools_for_user


_PLANNER_SYSTEM = (
    "You are a tool planner. Decide whether the user's request requires running a tool.\n"
    "Tools and their expected payloads (JSON):\n"
    "- queue.web.url: {\"urls\": string[]}\n"
    "- queue.web.website: {\"start_url\": string, \"allowed_prefixes\"?: string[], \"max_pages\"?: number}\n"
    "- queue.web.sitemap: {\"sitemap_url\": string, \"limit\"?: number}\n"
    "- queue.github.repo: {\"repo\": string, \"branch\"?: string, \"exts\"?: string[], \"chunk_size\"?: number, \"chunk_overlap\"?: number}\n"
    "- queue.github.org: {\"org\": string, \"visibility\"?: \"all\"|\"public\"|\"private\", \"include_archived\"?: boolean, \"topics\"?: string[], \"branch\"?: string, \"exts\"?: string[], \"chunk_size\"?: number, \"chunk_overlap\"?: number, \"limit\"?: number}\n"
    "If no tool is needed, respond with 'NONE' exactly.\n"
    "If a tool is needed, respond with a single fenced JSON block:\n"
    "```tool\\n{\"tool\":\"<name>\",\"payload\":{...}}\\n```\n"
    "No extra text, no explanation."
)


def plan_tool_call(answer_llm: callable, question: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Ask the LLM to propose a tool call for the question. Returns (name, payload) or None."""
    try:
        out = answer_llm(question, system_prompt=_PLANNER_SYSTEM)
    except Exception:
        return None
    out = (out or "").strip()
    if out.upper() == "NONE":
        return None
    tc = extract_tool_call(out)
    return tc


async def maybe_execute_tool_from_text(bot, message, question: str) -> bool:
    """Plan and execute a tool based on the question. Returns True if a tool was triggered."""
    from .config import settings as _settings  # type: ignore
    if not getattr(_settings, "tools_auto_enable", True):
        return False
    if not can_run_tools_for_user(message.author):
        return False
    # Use the same LLM provider as RAGService, via services.rag.answer_llm
    try:
        tc = plan_tool_call(lambda q, system_prompt: bot.services.rag.answer_llm(q, system_prompt=system_prompt), question)  # type: ignore[attr-defined]
    except Exception:
        tc = None
    if not tc:
        return False
    name, payload = tc
    import asyncio

    async def _run():
        try:
            res = await asyncio.to_thread(bot.services.tools.call, name, payload)  # type: ignore[attr-defined]
            await message.channel.send(f"🛠️ Tool '{name}' → {res.content}")  # type: ignore[union-attr]
        except Exception as e:
            await message.channel.send(f"🛠️ Tool '{name}' failed: {e}")  # type: ignore[union-attr]

    asyncio.create_task(_run())
    return True

