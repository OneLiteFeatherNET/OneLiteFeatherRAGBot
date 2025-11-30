from __future__ import annotations

from pathlib import Path
from typing import Optional
import asyncio
import asyncpg
from ..config import settings


# -------------------------
# File-based fallback store
# -------------------------

def _prompt_path() -> Path:
    root = Path(getattr(settings, "etl_staging_dir", ".staging"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "system_prompt.txt"


def _file_save_system_prompt(text: str | None) -> None:
    p = _prompt_path()
    if text is None or text.strip() == "":
        if p.exists():
            p.unlink(missing_ok=True)
        return
    p.write_text(text, encoding="utf-8")


def _file_load_system_prompt() -> str | None:
    p = _prompt_path()
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


# Scoped prompts (channel overrides guild, guild overrides global)
def _prompts_root() -> Path:
    root = Path(getattr(settings, "etl_staging_dir", ".staging")) / "prompts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _file_save_prompt_global(text: str | None) -> None:
    root = _prompts_root()
    p = root / "global.txt"
    if not text:
        p.unlink(missing_ok=True)
        return
    p.write_text(text, encoding="utf-8")


def _file_save_prompt_guild(guild_id: int, text: str | None) -> None:
    root = _prompts_root()
    p = root / f"guild-{guild_id}.txt"
    if not text:
        p.unlink(missing_ok=True)
        return
    p.write_text(text, encoding="utf-8")


def _file_save_prompt_channel(channel_id: int, text: str | None) -> None:
    root = _prompts_root()
    p = root / f"channel-{channel_id}.txt"
    if not text:
        p.unlink(missing_ok=True)
        return
    p.write_text(text, encoding="utf-8")


def _file_load_prompt_effective(guild_id: int | None, channel_id: int | None) -> str | None:
    root = _prompts_root()
    # channel override
    if channel_id is not None:
        pc = root / f"channel-{channel_id}.txt"
        if pc.exists():
            return pc.read_text(encoding="utf-8")
    # guild override
    if guild_id is not None:
        pg = root / f"guild-{guild_id}.txt"
        if pg.exists():
            return pg.read_text(encoding="utf-8")
    # global override
    pg = root / "global.txt"
    if pg.exists():
        return pg.read_text(encoding="utf-8")
    # fallback: legacy system_prompt.txt or env handled upstream
    return None


# -------------------------
# DB-based store (preferred)
# -------------------------

def _dsn() -> str:
    db = settings.db
    return f"postgresql://{db.user}:{db.password}@{db.host}:{db.port}/{db.database}"


async def _ensure_async(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_settings (
            scope TEXT NOT NULL,            -- 'global' | 'guild' | 'channel'
            scope_id BIGINT,                -- NULL for global
            key TEXT NOT NULL,              -- e.g., 'system_prompt'
            value TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(scope, scope_id, key)
        );
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


def _db_save(scope: str, scope_id: Optional[int], key: str, text: Optional[str]) -> None:
    async def run():
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            if text is None or text.strip() == "":
                await conn.execute(
                    "DELETE FROM rag_settings WHERE scope=$1 AND scope_id IS NOT DISTINCT FROM $2 AND key=$3",
                    scope,
                    scope_id,
                    key,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO rag_settings(scope, scope_id, key, value)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (scope, scope_id, key)
                    DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
                    """,
                    scope,
                    scope_id,
                    key,
                    text,
                )
        finally:
            await conn.close()

    asyncio.run(run())


def _db_load_effective(guild_id: Optional[int], channel_id: Optional[int]) -> Optional[str]:
    async def run() -> Optional[str]:
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            # channel override
            if channel_id is not None:
                row = await conn.fetchrow(
                    "SELECT value FROM rag_settings WHERE scope='channel' AND scope_id=$1 AND key='system_prompt'",
                    int(channel_id),
                )
                if row and row["value"]:
                    return str(row["value"])  # type: ignore[index]
            # guild override
            if guild_id is not None:
                row = await conn.fetchrow(
                    "SELECT value FROM rag_settings WHERE scope='guild' AND scope_id=$1 AND key='system_prompt'",
                    int(guild_id),
                )
                if row and row["value"]:
                    return str(row["value"])  # type: ignore[index]
            # global
            row = await conn.fetchrow(
                "SELECT value FROM rag_settings WHERE scope='global' AND scope_id IS NULL AND key='system_prompt'",
            )
            if row and row["value"]:
                return str(row["value"])  # type: ignore[index]
            return None
        finally:
            await conn.close()

    return asyncio.run(run())


# -------------------------
# Public API (switchable backend)
# -------------------------

def save_system_prompt(text: str | None) -> None:
    backend = (getattr(settings, "config_backend", "db") or "db").lower()
    if backend == "db":
        _db_save("global", None, "system_prompt", text)
    else:
        _file_save_system_prompt(text)


def load_system_prompt() -> str | None:
    backend = (getattr(settings, "config_backend", "db") or "db").lower()
    if backend == "db":
        return _db_load_effective(None, None)
    return _file_load_system_prompt()


def save_prompt_global(text: str | None) -> None:
    backend = (getattr(settings, "config_backend", "db") or "db").lower()
    if backend == "db":
        _db_save("global", None, "system_prompt", text)
    else:
        _file_save_prompt_global(text)


def save_prompt_guild(guild_id: int, text: str | None) -> None:
    backend = (getattr(settings, "config_backend", "db") or "db").lower()
    if backend == "db":
        _db_save("guild", int(guild_id), "system_prompt", text)
    else:
        _file_save_prompt_guild(guild_id, text)


def save_prompt_channel(channel_id: int, text: str | None) -> None:
    backend = (getattr(settings, "config_backend", "db") or "db").lower()
    if backend == "db":
        _db_save("channel", int(channel_id), "system_prompt", text)
    else:
        _file_save_prompt_channel(channel_id, text)


def load_prompt_effective(guild_id: int | None, channel_id: int | None) -> str | None:
    backend = (getattr(settings, "config_backend", "db") or "db").lower()
    if backend == "db":
        return _db_load_effective(guild_id, channel_id)
    return _file_load_prompt_effective(guild_id, channel_id)
