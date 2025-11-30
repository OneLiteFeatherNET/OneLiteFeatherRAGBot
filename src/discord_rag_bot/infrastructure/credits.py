from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional, Tuple

import asyncpg

from ..config import settings


def _dsn() -> str:
    db = settings.db
    return f"postgresql://{db.user}:{db.password}@{db.host}:{db.port}/{db.database}"


def _period_start(dt: Optional[datetime] = None) -> datetime:
    dt = dt or datetime.now(timezone.utc)
    # Monthly period boundary (first day of month at 00:00 UTC)
    return datetime(dt.year, dt.month, 1, tzinfo=timezone.utc)


async def _ensure_async(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_credits_user (
            user_id BIGINT NOT NULL,
            period_start TIMESTAMPTZ NOT NULL,
            used_credits INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, period_start)
        );
        CREATE INDEX IF NOT EXISTS idx_bot_credits_user_period ON bot_credits_user(period_start);
        CREATE TABLE IF NOT EXISTS bot_credits_global (
            period_start TIMESTAMPTZ PRIMARY KEY,
            used_credits INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS bot_credit_user_limits (
            user_id BIGINT PRIMARY KEY,
            user_limit INTEGER NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS bot_credit_unlimited_roles (
            role_id BIGINT PRIMARY KEY,
            role_name TEXT,
            guild_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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


def _credits_for_text_chars(in_chars: int, out_est_tokens: int) -> int:
    tokens_in = int(round(in_chars * float(settings.credit_tokens_per_char)))
    tokens_total = tokens_in + int(out_est_tokens)
    per_k = float(settings.credit_per_1k_tokens) or 1.0
    # credits ~ tokens_total / 1000 * per_k
    credits = int((tokens_total + 999) // 1000 * per_k)
    return max(1, credits)


def estimate_credits_for_question(question: str) -> int:
    return _credits_for_text_chars(len(question or ""), int(settings.credit_est_output_tokens))


def pre_authorize(user_id: int, est_credits: int, *, now: Optional[datetime] = None, user_limit_override: Optional[int] = None) -> Tuple[bool, int, int]:
    """Reserve credits if within per-user limit and global cap.

    Returns (ok, user_used_after, global_used_after). If ok is False, no change.
    """
    period = _period_start(now)

    async def run() -> Tuple[bool, int, int]:
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            async with conn.transaction():
                # Load current usage
                row_u = await conn.fetchrow(
                    "SELECT used_credits FROM bot_credits_user WHERE user_id=$1 AND period_start=$2",
                    int(user_id),
                    period,
                )
                user_used = int(row_u[0]) if row_u else 0
                row_g = await conn.fetchrow(
                    "SELECT used_credits FROM bot_credits_global WHERE period_start=$1",
                    period,
                )
                global_used = int(row_g[0]) if row_g else 0

                user_limit = int(user_limit_override or settings.credit_default_limit)
                # Limit can be overridden by ranks; resolved outside and passed? For now use default; the caller can pass a higher est or pre-check limit.
                # Enforce limits
                if settings.credit_enabled:
                    if user_used + est_credits > user_limit:
                        return False, user_used, global_used
                    if global_used + est_credits > int(settings.credit_global_cap):
                        return False, user_used, global_used

                # Upsert increments
                await conn.execute(
                    """
                    INSERT INTO bot_credits_user(user_id, period_start, used_credits)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, period_start)
                    DO UPDATE SET used_credits = bot_credits_user.used_credits + EXCLUDED.used_credits, updated_at=NOW()
                    """,
                    int(user_id),
                    period,
                    int(est_credits),
                )
                await conn.execute(
                    """
                    INSERT INTO bot_credits_global(period_start, used_credits)
                    VALUES ($1, $2)
                    ON CONFLICT (period_start)
                    DO UPDATE SET used_credits = bot_credits_global.used_credits + EXCLUDED.used_credits, updated_at=NOW()
                    """,
                    period,
                    int(est_credits),
                )
                return True, user_used + est_credits, global_used + est_credits
        finally:
            await conn.close()

    return asyncio.run(run())


def adjust_usage(user_id: int, delta: int, *, now: Optional[datetime] = None) -> None:
    """Adjust usage by delta (can be negative). Best-effort."""
    if delta == 0:
        return
    period = _period_start(now)

    async def run():
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO bot_credits_user(user_id, period_start, used_credits)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, period_start)
                    DO UPDATE SET used_credits = GREATEST(0, bot_credits_user.used_credits + EXCLUDED.used_credits), updated_at=NOW()
                    """,
                    int(user_id), period, int(delta)
                )
                await conn.execute(
                    """
                    INSERT INTO bot_credits_global(period_start, used_credits)
                    VALUES ($1, $2)
                    ON CONFLICT (period_start)
                    DO UPDATE SET used_credits = GREATEST(0, bot_credits_global.used_credits + EXCLUDED.used_credits), updated_at=NOW()
                    """,
                    period, int(delta)
                )
        finally:
            await conn.close()

    asyncio.run(run())


def resolve_user_limit_from_roles(*, member_roles: list[tuple[int, str]]) -> int:
    """Compute per-user credit limit based on configured rank mappings and role names/ids.

    member_roles: list of (role_id, role_name)
    """
    # Determine rank candidates from roles
    by_name = settings.credit_role_ranks_by_name or {}
    by_id = settings.credit_role_ranks_by_id or {}
    ranks: set[str] = set()
    for rid, name in member_roles:
        if name and name in by_name:
            ranks.add(by_name[name])
        s_rid = str(rid)
        if s_rid in by_id:
            ranks.add(by_id[s_rid])
    # Map ranks to limits and take max
    rank_limits = settings.credit_rank_limits or {}
    max_limit = int(settings.credit_default_limit)
    for r in ranks:
        lim = rank_limits.get(r)
        if isinstance(lim, int) and lim > max_limit:
            max_limit = lim
    return max_limit


def has_unlimited_from_roles(*, member_roles: list[tuple[int, str]]) -> bool:
    # From settings
    names = set((settings.credit_unlimited_role_names or []))
    ids = set(int(x) for x in (settings.credit_unlimited_role_ids or []))
    for rid, name in member_roles:
        if rid in ids:
            return True
        if name and name in names:
            return True
    # From DB
    async def run() -> bool:
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            role_ids = [int(rid) for rid, _ in member_roles if rid]
            if not role_ids:
                return False
            rows = await conn.fetch(
                "SELECT role_id FROM bot_credit_unlimited_roles WHERE role_id = ANY($1::BIGINT[])",
                role_ids,
            )
            return bool(rows)
        finally:
            await conn.close()

    return asyncio.run(run())


def get_user_limit_override(user_id: int) -> Optional[int]:
    async def run() -> Optional[int]:
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            try:
                row = await conn.fetchrow("SELECT user_limit FROM bot_credit_user_limits WHERE user_id=$1", int(user_id))
                return int(row[0]) if row else None
            except Exception:
                # Backward compatibility if column was previously named reserved word "limit"
                row = await conn.fetchrow("SELECT \"limit\" FROM bot_credit_user_limits WHERE user_id=$1", int(user_id))
                return int(row[0]) if row else None
        finally:
            await conn.close()

    return asyncio.run(run())


def set_user_limit(user_id: int, limit: int) -> None:
    async def run():
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            # Try with new column name first; fallback for legacy column if needed
            try:
                await conn.execute(
                    """
                    INSERT INTO bot_credit_user_limits(user_id, user_limit)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE SET user_limit=EXCLUDED.user_limit, updated_at=NOW()
                    """,
                    int(user_id), int(limit)
                )
            except Exception:
                # Legacy fallback when the column was named "limit" (reserved keyword)
                await conn.execute(
                    """
                    INSERT INTO bot_credit_user_limits(user_id, "limit")
                    VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE SET "limit"=EXCLUDED."limit", updated_at=NOW()
                    """,
                    int(user_id), int(limit)
                )
        finally:
            await conn.close()

    asyncio.run(run())


def clear_user_limit(user_id: int) -> None:
    async def run():
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            await conn.execute("DELETE FROM bot_credit_user_limits WHERE user_id=$1", int(user_id))
        finally:
            await conn.close()

    asyncio.run(run())


def add_unlimited_role(role_id: int, role_name: Optional[str], guild_id: Optional[int]) -> None:
    async def run():
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            await conn.execute(
                """
                INSERT INTO bot_credit_unlimited_roles(role_id, role_name, guild_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (role_id) DO UPDATE SET role_name=EXCLUDED.role_name, guild_id=EXCLUDED.guild_id
                """,
                int(role_id), role_name, int(guild_id) if guild_id else None
            )
        finally:
            await conn.close()

    asyncio.run(run())


def remove_unlimited_role(role_id: int) -> None:
    async def run():
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            await conn.execute("DELETE FROM bot_credit_unlimited_roles WHERE role_id=$1", int(role_id))
        finally:
            await conn.close()

    asyncio.run(run())


def list_unlimited_roles() -> list[tuple[int, Optional[str], Optional[int]]]:
    async def run() -> list[tuple[int, Optional[str], Optional[int]]]:
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            rows = await conn.fetch("SELECT role_id, role_name, guild_id FROM bot_credit_unlimited_roles ORDER BY created_at")
            out: list[tuple[int, Optional[str], Optional[int]]] = []
            for r in rows:
                out.append((int(r["role_id"]), r["role_name"], int(r["guild_id"]) if r["guild_id"] else None))
            return out
        finally:
            await conn.close()

    return asyncio.run(run())


def get_usage(user_id: int) -> tuple[int, int]:
    """Return (user_used, global_used) for current period."""
    period = _period_start()

    async def run() -> tuple[int, int]:
        conn = await asyncpg.connect(_dsn())
        try:
            await _ensure_async(conn)
            row_u = await conn.fetchrow("SELECT used_credits FROM bot_credits_user WHERE user_id=$1 AND period_start=$2", int(user_id), period)
            row_g = await conn.fetchrow("SELECT used_credits FROM bot_credits_global WHERE period_start=$1", period)
            return (int(row_u[0]) if row_u else 0, int(row_g[0]) if row_g else 0)
        finally:
            await conn.close()

    return asyncio.run(run())


def compute_user_policy(*, user_id: int, member_roles: list[tuple[int, str]], is_admin: bool) -> tuple[bool, int]:
    """Return (unlimited, per_user_limit).

    unlimited ignores per-user limit but still respects global cap.
    """
    # Admins unlimited by default
    if is_admin:
        return True, 10**9
    if has_unlimited_from_roles(member_roles=member_roles):
        return True, 10**9
    # Per-user override
    ul = get_user_limit_override(user_id)
    if isinstance(ul, int):
        return False, max(1, int(ul))
    # Rank-based
    limit = resolve_user_limit_from_roles(member_roles=member_roles)
    return False, max(1, int(limit))
