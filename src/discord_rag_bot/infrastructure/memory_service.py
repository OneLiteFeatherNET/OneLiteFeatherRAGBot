from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Tuple
from abc import ABC, abstractmethod

from .memory import (
    ensure_store as legacy_ensure_store,
    save_message as legacy_save_message,
    load_slice as legacy_load_slice,
    update_summary_with_ai as legacy_update_summary_with_ai,
)
from ..config import settings


@dataclass
class MemoryContext:
    summary: Optional[str]
    recent: List[Tuple[str, str]]  # (role, content)


class MemoryService(ABC):
    @abstractmethod
    def ensure(self) -> None:
        ...

    @abstractmethod
    def record_user_message(self, *, user_id: int, guild_id: Optional[int], channel_id: Optional[int], content: str) -> None:
        ...

    @abstractmethod
    def record_assistant_message(self, *, user_id: int, guild_id: Optional[int], channel_id: Optional[int], content: str) -> None:
        ...

    @abstractmethod
    def get_context(self, *, user_id: int, channel_id: Optional[int], limit: int = 8) -> MemoryContext:
        ...

    @abstractmethod
    def update_summary(self, *, user_id: int, user_text: str, bot_answer: str, answer_llm: callable) -> Optional[str]:
        ...


class FallbackMemoryService(MemoryService):
    """Existing Postgres-backed memory implementation as a fallback."""

    def ensure(self) -> None:
        try:
            legacy_ensure_store()
        except Exception:
            pass

    def record_user_message(self, *, user_id: int, guild_id: Optional[int], channel_id: Optional[int], content: str) -> None:
        legacy_save_message(user_id=user_id, guild_id=guild_id, channel_id=channel_id, role="user", content=content)

    def record_assistant_message(self, *, user_id: int, guild_id: Optional[int], channel_id: Optional[int], content: str) -> None:
        legacy_save_message(user_id=user_id, guild_id=guild_id, channel_id=channel_id, role="assistant", content=content)

    def get_context(self, *, user_id: int, channel_id: Optional[int], limit: int = 8) -> MemoryContext:
        sl = legacy_load_slice(user_id=user_id, channel_id=channel_id, limit=limit)
        return MemoryContext(summary=sl.summary, recent=sl.recent)

    def update_summary(self, *, user_id: int, user_text: str, bot_answer: str, answer_llm: callable) -> Optional[str]:
        updated = legacy_update_summary_with_ai(current_summary=self.get_context(user_id=user_id, channel_id=None).summary, user_text=user_text, bot_answer=bot_answer, answer_llm=answer_llm)
        if updated and updated.strip():
            legacy_save_message(user_id=user_id, guild_id=None, channel_id=None, role="summary", content=updated.strip(), kind="summary")
        return updated


class LlamaIndexMemoryService(MemoryService):
    """LlamaIndex ChatMemory with SQLChatStore persistence.

    Falls back to FallbackMemoryService if LlamaIndex APIs are unavailable at runtime.
    """

    def __init__(self, token_limit: int = 2048) -> None:
        self._token_limit = token_limit
        self._fallback = FallbackMemoryService()
        # Lazy init imports to minimize hard dependency during import time
        try:
            from llama_index.core.storage.chat_store import SQLChatStore  # type: ignore
            # Try both import paths for ChatMessage/MessageRole
            try:
                from llama_index.core.llms import ChatMessage, MessageRole  # type: ignore
            except Exception:  # pragma: no cover - version compatibility
                from llama_index.core.llms.types import ChatMessage, MessageRole  # type: ignore
            from llama_index.core.memory import ChatMemoryBuffer  # type: ignore
        except Exception as e:  # pragma: no cover - if not available
            # Keep attributes for type checkers, but mark as None at runtime
            self._SQLChatStore = None
            self._ChatMessage = None
            self._MessageRole = None
            self._ChatMemoryBuffer = None
            self._err = e
            return

        self._SQLChatStore = SQLChatStore  # type: ignore[assignment]
        self._ChatMessage = ChatMessage  # type: ignore[assignment]
        self._MessageRole = MessageRole  # type: ignore[assignment]
        self._ChatMemoryBuffer = ChatMemoryBuffer  # type: ignore[assignment]
        self._err = None
        self._store = None
        self._buffers: dict[str, object] = {}

    def _enabled(self) -> bool:
        return self._SQLChatStore is not None and self._ChatMemoryBuffer is not None

    def _dsn(self) -> str:
        db = settings.db
        return f"postgresql://{db.user}:{db.password}@{db.host}:{db.port}/{db.database}"

    def ensure(self) -> None:
        if not self._enabled():
            self._fallback.ensure()
            return
        try:
            # Initialize store; SQLChatStore will ensure tables
            if self._store is None:
                self._store = self._SQLChatStore(self._dsn())  # type: ignore[operator]
        except Exception:
            # Fall back if SQLChatStore fails
            self._fallback.ensure()

    def _key(self, user_id: int, channel_id: Optional[int]) -> str:
        return f"user:{user_id}:chan:{channel_id or 'global'}"

    def _summary_key(self, user_id: int) -> str:
        return f"summary:user:{user_id}"

    def _get_buffer(self, key: str):
        if not self._enabled() or self._store is None:
            return None
        buf = self._buffers.get(key)
        if buf is None:
            buf = self._ChatMemoryBuffer.from_defaults(
                token_limit=self._token_limit,
                chat_store=self._store,
                chat_store_key=key,
            )
            self._buffers[key] = buf
        return buf

    def record_user_message(self, *, user_id: int, guild_id: Optional[int], channel_id: Optional[int], content: str) -> None:
        if not self._enabled() or self._store is None:
            self._fallback.record_user_message(user_id=user_id, guild_id=guild_id, channel_id=channel_id, content=content)
            return
        try:
            key = self._key(user_id, channel_id)
            buf = self._get_buffer(key)
            if buf is None:
                raise RuntimeError("buffer unavailable")
            # Prefer storing explicit user role
            msg = self._ChatMessage(role=self._MessageRole.USER, content=content)
            # SQLChatStore has add_message API; through memory buffer we can append too
            self._store.add_message(key, msg)
        except Exception:
            self._fallback.record_user_message(user_id=user_id, guild_id=guild_id, channel_id=channel_id, content=content)

    def record_assistant_message(self, *, user_id: int, guild_id: Optional[int], channel_id: Optional[int], content: str) -> None:
        if not self._enabled() or self._store is None:
            self._fallback.record_assistant_message(user_id=user_id, guild_id=guild_id, channel_id=channel_id, content=content)
            return
        try:
            key = self._key(user_id, channel_id)
            buf = self._get_buffer(key)
            if buf is None:
                raise RuntimeError("buffer unavailable")
            msg = self._ChatMessage(role=self._MessageRole.ASSISTANT, content=content)
            self._store.add_message(key, msg)
        except Exception:
            self._fallback.record_assistant_message(user_id=user_id, guild_id=guild_id, channel_id=channel_id, content=content)

    def get_context(self, *, user_id: int, channel_id: Optional[int], limit: int = 8) -> MemoryContext:
        if not self._enabled() or self._store is None:
            return self._fallback.get_context(user_id=user_id, channel_id=channel_id, limit=limit)
        try:
            key = self._key(user_id, channel_id)
            # get recent messages from store
            msgs = self._store.get_messages(key) or []
            tuples: List[Tuple[str, str]] = []
            for m in msgs[-limit:]:  # type: ignore[index]
                # m has .role and .content
                role = getattr(m, "role", None)
                content = getattr(m, "content", None)
                if role is None or content is None:
                    continue
                r = str(role)
                # Normalize role
                if ":" in r:
                    r = r.split(":")[-1]
                r = r.lower()
                tuples.append((r, str(content)))
            # summary stored under dedicated key
            skey = self._summary_key(user_id)
            s_msgs = self._store.get_messages(skey) or []
            summary = None
            if s_msgs:
                last = s_msgs[-1]
                summary = str(getattr(last, "content", "")) or None
            return MemoryContext(summary=summary, recent=tuples)
        except Exception:
            return self._fallback.get_context(user_id=user_id, channel_id=channel_id, limit=limit)

    def update_summary(self, *, user_id: int, user_text: str, bot_answer: str, answer_llm: callable) -> Optional[str]:
        # Compute via existing summarizer and persist in chat store
        updated = legacy_update_summary_with_ai(current_summary=self.get_context(user_id=user_id, channel_id=None).summary, user_text=user_text, bot_answer=bot_answer, answer_llm=answer_llm)
        if not updated or not updated.strip():
            return updated
        if not self._enabled() or self._store is None:
            # fallback persistence
            legacy_save_message(user_id=user_id, guild_id=None, channel_id=None, role="summary", content=updated.strip(), kind="summary")
            return updated
        try:
            try:
                # Try role SYSTEM for summary
                msg = self._ChatMessage(role=self._MessageRole.SYSTEM, content=updated.strip())
            except Exception:
                # Older versions may not have SYSTEM → use ASSISTANT
                msg = self._ChatMessage(role=self._MessageRole.ASSISTANT, content=updated.strip())
            self._store.add_message(self._summary_key(user_id), msg)
        except Exception:
            legacy_save_message(user_id=user_id, guild_id=None, channel_id=None, role="summary", content=updated.strip(), kind="summary")
        return updated


def build_memory_service() -> MemoryService:
    # Default: try LlamaIndex-backed service; fallback to legacy on any issue
    try:
        svc = LlamaIndexMemoryService(token_limit=2048)
        svc.ensure()
        return svc
    except Exception:
        fb = FallbackMemoryService()
        fb.ensure()
        return fb

