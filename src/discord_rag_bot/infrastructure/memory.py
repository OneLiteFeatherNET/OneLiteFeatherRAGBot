from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, Sequence

import asyncpg

from ..config import settings


def _dsn() -> str:
    db = settings.db
    return f"postgresql://{db.user}:{db.password}@{db.host}:{db.port}/{db.database}"


async def _ensure_async(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_memory (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            guild_id BIGINT,
            channel_id BIGINT,
            role TEXT NOT NULL,          -- 'user' | 'assistant' | 'system' | 'summary'
            kind TEXT NOT NULL DEFAULT 'message',
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_bot_memory_user_chan_time ON bot_memory(user_id, channel_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_bot_memory_user_time ON bot_memory(user_id, created_at DESC);
        """
    )


def ensure_store() -> None:
    async def run():
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
        finally:
            await conn.close()

    asyncio.run(run())


def save_message(*, user_id: int, guild_id: Optional[int], channel_id: Optional[int], role: str, content: str, kind: str = "message") -> None:
    async def run():
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            await conn.execute(
                """
                INSERT INTO bot_memory(user_id, guild_id, channel_id, role, kind, content)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                int(user_id),
                int(guild_id) if guild_id is not None else None,
                int(channel_id) if channel_id is not None else None,
                role,
                kind,
                content,
            )
        finally:
            await conn.close()

    asyncio.run(run())


@dataclass
class MemorySlice:
    summary: Optional[str]
    recent: list[tuple[str, str]]  # list of (role, content)


def load_slice(*, user_id: int, channel_id: Optional[int], limit: int = 8) -> MemorySlice:
    async def run() -> MemorySlice:
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            # summary (latest)
            row = await conn.fetchrow(
                """
                SELECT content FROM bot_memory
                WHERE user_id=$1 AND role='summary'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                int(user_id),
            )
            summary = str(row["content"]) if row and row["content"] else None

            # recent conversation in channel (user/assistant roles)
            if channel_id is not None:
                rows: Sequence[asyncpg.Record] = await conn.fetch(
                    """
                    SELECT role, content FROM bot_memory
                    WHERE user_id=$1 AND channel_id=$2 AND role IN ('user','assistant')
                    ORDER BY created_at DESC
                    LIMIT $3
                    """,
                    int(user_id),
                    int(channel_id),
                    int(limit),
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT role, content FROM bot_memory
                    WHERE user_id=$1 AND role IN ('user','assistant')
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    int(user_id),
                    int(limit),
                )
            recent = [(str(r["role"]), str(r["content"])) for r in rows]
            recent.reverse()  # chronological
            return MemorySlice(summary=summary, recent=list(recent))
        finally:
            await conn.close()

    return asyncio.run(run())


def clear_channel(*, user_id: int, channel_id: int) -> int:
    async def run() -> int:
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            res = await conn.execute(
                """
                DELETE FROM bot_memory
                WHERE user_id=$1 AND channel_id=$2 AND role IN ('user','assistant')
                """,
                int(user_id),
                int(channel_id),
            )
            # res like 'DELETE <n>'
            try:
                return int(str(res).split()[-1])
            except Exception:
                return 0
        finally:
            await conn.close()

    return asyncio.run(run())


def clear_all(*, user_id: int) -> int:
    async def run() -> int:
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            res = await conn.execute(
                """
                DELETE FROM bot_memory
                WHERE user_id=$1
                """,
                int(user_id),
            )
            try:
                return int(str(res).split()[-1])
            except Exception:
                return 0
        finally:
            await conn.close()

    return asyncio.run(run())



def update_summary_with_ai(*, current_summary: Optional[str], user_text: str, bot_answer: str, answer_llm: callable) -> Optional[str]:
    """Use the LLM to keep a concise user memory summary.

    answer_llm: callable(question: str, system_prompt: Optional[str]) -> str
    """
    sys_prompt = (
        "Du bist ein Assistent, der eine kurze, stichpunktartige Nutzer-Zusammenfassung pflegt.\n"
        "Extrahiere nur langlebige Fakten, Präferenzen, Schreibstil/Emoji-Vorlieben, Sprache, wichtige Kontexte.\n"
        "Halte es knapp (max. ~6 Stichpunkte), keine PII, nichts Sensibles. Aktualisiere konsistent.\n"
    )
    base = current_summary or "(leer)"
    question = (
        "Aktualisiere diese Nutzer-Zusammenfassung auf Basis der neuen Interaktion.\n\n"
        f"Bisherige Zusammenfassung:\n{base}\n\n"
        f"Neue Nachricht des Nutzers:\n{user_text}\n\n"
        f"Antwort des Bots:\n{bot_answer}"
    )
    try:
        updated = answer_llm(question, system_prompt=sys_prompt)
        return updated.strip()
    except Exception:
        return None
