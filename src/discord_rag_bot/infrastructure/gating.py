from __future__ import annotations

from typing import Optional
import json
from ..config import settings
from llama_index.core import Settings


def _llm_decide_use_rag(question: str, *, guild_name: Optional[str], channel_name: Optional[str]) -> bool:
    """Ask the LLM to decide whether RAG is needed for this message.

    Returns True if the LLM indicates retrieval is needed, False otherwise.
    """
    sys = (
        "Du bist ein Klassifizierer. Entscheide, ob für die Nachricht Wissens-"
        "recherche (RAG) nötig ist. Antworte NUR als kompaktes JSON: {\"use_rag\": true|false, \"reason\": \"...\"}. "
        "Nutze RAG für projekt-/dokumentationsbezogene Fragen (Code, Config, API, Fehler, Versionen, Links). "
        "Kein RAG für Smalltalk, Begrüßung, Identitätsfragen über den Bot, reine Meta-/Test-Anfragen. "
        "Bei Unklarheit: use_rag=false."
    )
    user = (
        f"Nachricht: {question}\n"
        f"Gilde: {guild_name or '-'}\n"
        f"Kanal: {channel_name or '-'}\n"
        "Antworte nur mit JSON."
    )
    try:
        llm = Settings.llm
        prompt = f"System:\n{sys}\n\nUser:\n{user}"
        resp = llm.complete(prompt)
        text = str(resp).strip()
        # Tolerant JSON-Parsing (extrahiere erstes {...})
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            js = text[start : end + 1]
            data = json.loads(js)
            return bool(data.get("use_rag", False))
    except Exception:
        # Fallback: konservativ, kein RAG
        return False
    return False


def should_use_rag(
    question: str,
    *,
    guild_name: Optional[str] = None,
    channel_name: Optional[str] = None,
    best_score: Optional[float] = None,
    score_kind: str = "similarity",
    sources_count: int = 0,
) -> bool:
    mode = (settings.rag_mode or "auto").lower()
    if mode == "rag":
        return True
    if mode == "llm":
        return False

    strategy = (getattr(settings, "rag_gate_strategy", "llm") or "llm").lower()
    if strategy == "llm":
        return _llm_decide_use_rag(question, guild_name=guild_name, channel_name=channel_name)

    gate_thr = settings.rag_gate_threshold if settings.rag_gate_threshold is not None else settings.rag_mix_threshold
    if best_score is not None and sources_count > 0 and gate_thr is not None:
        if score_kind == "similarity":
            return best_score >= float(gate_thr)
        return best_score <= float(gate_thr)

    return False
