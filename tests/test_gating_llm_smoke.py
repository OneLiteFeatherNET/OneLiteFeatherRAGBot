from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from llama_index.core import Settings

from discord_rag_bot.infrastructure.gating import should_use_rag


class _FakeResp:
    def __init__(self, text: str):
        self._text = text

    def __str__(self) -> str:
        return self._text


class _FakeLLM:
    def complete(self, prompt: str, **_: Any):  # type: ignore[override]
        p = prompt.lower()
        # Simple rule-of-thumb for smoke testing:
        # - code/config/api related → use_rag true
        # - greetings/meta/identity/test → use_rag false
        positives = [
            "config",
            "plugin.yml",
            "api",
            "fehler",
            "stacktrace",
            "gradle",
            "maven",
            "github",
            "javadoc",
        ]
        negatives = [
            "hi",
            "hallo",
            "wer bist du",
            "wo bist du",
            "hilfe",
            "test",
            "ping",
        ]
        if any(w in p for w in positives):
            return _FakeResp('{"use_rag": true, "reason": "domain docs"}')
        if any(w in p for w in negatives):
            return _FakeResp('{"use_rag": false, "reason": "smalltalk"}')
        # default conservative
        return _FakeResp('{"use_rag": false, "reason": "unsure"}')


@contextmanager
def _patched_llm(fake):
    prev = Settings.llm
    Settings.llm = fake
    try:
        yield
    finally:
        Settings.llm = prev


def test_llm_gating_smalltalk_false():
    with _patched_llm(_FakeLLM()):
        use = should_use_rag("Hi, wer bist du?", guild_name="OneLiteFeather", channel_name="general")
        assert use is False


def test_llm_gating_docs_true():
    with _patched_llm(_FakeLLM()):
        use = should_use_rag("Wie konfiguriere ich die plugin.yml?", guild_name="OneLiteFeather", channel_name="support")
        assert use is True

