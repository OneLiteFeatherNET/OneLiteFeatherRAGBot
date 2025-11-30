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
