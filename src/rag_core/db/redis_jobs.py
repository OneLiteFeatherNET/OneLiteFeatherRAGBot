from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import JobRepository, Job


class RedisJobRepository(JobRepository):
    """Redis-backed JobRepository.

    - Uses Redis for job metadata and a list for the pending queue.
    - Keys (namespace = ns):
        ns:jobs:next_id            -> INCR for new IDs
        ns:job:<id>                -> HASH with fields (type, payload JSON, status, attempts, timestamps, progress_*)
        ns:queue:pending           -> LIST of job IDs (strings)
        ns:idx:all                 -> ZSET of job IDs scored by created_at epoch
        ns:idx:status:<status>     -> ZSET per status, scored by last updated epoch
    """

    def __init__(self, url: str, namespace: str = "rag") -> None:
        self.url = url
        self.ns = namespace

    async def _r(self):  # lazy import
        try:
            import redis.asyncio as redis  # type: ignore
        except Exception as e:  # pragma: no cover - optional dependency
            raise RuntimeError("redis-py not installed. Install 'redis' package to use RedisJobRepository") from e
        return redis.from_url(self.url, encoding="utf-8", decode_responses=True)

    def _k(self, name: str) -> str:
        return f"{self.ns}:{name}"

    @staticmethod
    def _now() -> float:
        return float(time.time())

    @staticmethod
    def _iso(ts: Optional[float]) -> Optional[str]:
        return datetime.fromtimestamp(ts).isoformat() if ts else None

    @staticmethod
    def _parse_iso(s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return None

    @staticmethod
    def _job_from_hash(h: Dict[str, Any]) -> Job:
        payload_raw = h.get("payload")
        payload: Dict[str, Any]
        if isinstance(payload_raw, str):
            try:
                payload = json.loads(payload_raw)
            except Exception:  # pragma: no cover
                payload = {"_raw": payload_raw}
        else:
            payload = payload_raw or {}
        def _int(v, default=None):
            try:
                return int(v) if v is not None else default
            except Exception:
                return default
        return Job(
            id=_int(h.get("id"), 0) or 0,
            type=h.get("type") or "",
            payload=payload,
            status=h.get("status") or "pending",
            attempts=_int(h.get("attempts"), 0) or 0,
            error=h.get("error"),
            created_at=RedisJobRepository._parse_iso(h.get("created_at")),
            started_at=RedisJobRepository._parse_iso(h.get("started_at")),
            finished_at=RedisJobRepository._parse_iso(h.get("finished_at")),
            progress_done=_int(h.get("progress_done")),
            progress_total=_int(h.get("progress_total")),
            progress_note=h.get("progress_note"),
        )

    async def ensure(self) -> None:
        r = await self._r()
        try:
            await r.ping()
        finally:
            if hasattr(r, "close"):
                await r.close()

    async def enqueue(self, job_type: str, payload: Dict[str, Any]) -> int:
        r = await self._r()
        try:
            job_id = int(await r.incr(self._k("jobs:next_id")))
            now = self._now()
            hkey = self._k(f"job:{job_id}")
            data = {
                "id": job_id,
                "type": job_type,
                "payload": json.dumps(payload, ensure_ascii=False),
                "status": "pending",
                "attempts": 0,
                "error": "",
                "created_at": self._iso(now),
                "started_at": "",
                "finished_at": "",
                "progress_done": "",
                "progress_total": "",
                "progress_note": "",
            }
            await r.hset(hkey, mapping={k: str(v) for k, v in data.items()})
            await r.lpush(self._k("queue:pending"), str(job_id))
            await r.zadd(self._k("idx:all"), {str(job_id): now})
            await r.zadd(self._k("idx:status:pending"), {str(job_id): now})
            return job_id
        finally:
            if hasattr(r, "close"):
                await r.close()

    async def fetch_and_start(self) -> Optional[Job]:
        r = await self._r()
        try:
            jid = await r.rpop(self._k("queue:pending"))
            if not jid:
                return None
            hkey = self._k(f"job:{jid}")
            now = self._now()
            pipe = r.pipeline()
            pipe.hincrby(hkey, "attempts", 1)
            pipe.hset(hkey, mapping={
                "status": "processing",
                "started_at": self._iso(now),
            })
            pipe.zrem(self._k("idx:status:pending"), jid)
            pipe.zadd(self._k("idx:status:processing"), {jid: now})
            await pipe.execute()
            data = await r.hgetall(hkey)
            return self._job_from_hash(data)
        finally:
            if hasattr(r, "close"):
                await r.close()

    async def list(self, limit: int = 20, status: Optional[str] = None) -> List[Job]:
        r = await self._r()
        try:
            ids: List[str]
            if status:
                ids = await r.zrevrange(self._k(f"idx:status:{status}"), 0, max(0, limit - 1))
            else:
                ids = await r.zrevrange(self._k("idx:all"), 0, max(0, limit - 1))
            if not ids:
                return []
            pipe = r.pipeline()
            for jid in ids:
                pipe.hgetall(self._k(f"job:{jid}"))
            rows = await pipe.execute()
            out: List[Job] = []
            for h in rows:
                if not h:
                    continue
                out.append(self._job_from_hash(h))
            return out
        finally:
            if hasattr(r, "close"):
                await r.close()

    async def get(self, job_id: int) -> Optional[Job]:
        r = await self._r()
        try:
            data = await r.hgetall(self._k(f"job:{job_id}"))
            if not data:
                return None
            return self._job_from_hash(data)
        finally:
            if hasattr(r, "close"):
                await r.close()

    async def complete(self, job_id: int) -> None:
        r = await self._r()
        try:
            now = self._now()
            hkey = self._k(f"job:{job_id}")
            pipe = r.pipeline()
            pipe.hset(hkey, mapping={
                "status": "completed",
                "finished_at": self._iso(now),
                "error": "",
            })
            jid = str(job_id)
            pipe.zrem(self._k("idx:status:processing"), jid)
            pipe.zadd(self._k("idx:status:completed"), {jid: now})
            await pipe.execute()
        finally:
            if hasattr(r, "close"):
                await r.close()

    async def fail(self, job_id: int, error: str) -> None:
        r = await self._r()
        try:
            now = self._now()
            hkey = self._k(f"job:{job_id}")
            pipe = r.pipeline()
            pipe.hset(hkey, mapping={
                "status": "failed",
                "finished_at": self._iso(now),
                "error": error,
            })
            jid = str(job_id)
            pipe.zrem(self._k("idx:status:processing"), jid)
            pipe.zadd(self._k("idx:status:failed"), {jid: now})
            await pipe.execute()
        finally:
            if hasattr(r, "close"):
                await r.close()

    async def retry(self, job_id: int) -> bool:
        r = await self._r()
        try:
            hkey = self._k(f"job:{job_id}")
            status = await r.hget(hkey, "status")
            if status not in ("failed", "canceled"):
                return False
            now = self._now()
            pipe = r.pipeline()
            pipe.hset(hkey, mapping={
                "status": "pending",
                "started_at": "",
                "finished_at": "",
                "error": "",
            })
            jid = str(job_id)
            pipe.lpush(self._k("queue:pending"), jid)
            pipe.zrem(self._k(f"idx:status:{status}"), jid)
            pipe.zadd(self._k("idx:status:pending"), {jid: now})
            await pipe.execute()
            return True
        finally:
            if hasattr(r, "close"):
                await r.close()

    async def cancel(self, job_id: int) -> bool:
        r = await self._r()
        try:
            hkey = self._k(f"job:{job_id}")
            status = await r.hget(hkey, "status")
            if status not in ("pending", "processing"):
                return False
            now = self._now()
            jid = str(job_id)
            pipe = r.pipeline()
            # Best-effort remove from pending queue
            pipe.lrem(self._k("queue:pending"), 1, jid)
            pipe.hset(hkey, mapping={
                "status": "canceled",
                "finished_at": self._iso(now),
            })
            pipe.zrem(self._k(f"idx:status:{status}"), jid)
            pipe.zadd(self._k("idx:status:canceled"), {jid: now})
            await pipe.execute()
            return True
        finally:
            if hasattr(r, "close"):
                await r.close()

    async def update_progress(self, job_id: int, *, done: int | None = None, total: int | None = None, note: str | None = None) -> None:
        r = await self._r()
        try:
            hkey = self._k(f"job:{job_id}")
            mapping: Dict[str, str] = {}
            if done is not None:
                mapping["progress_done"] = str(done)
            if total is not None:
                mapping["progress_total"] = str(total)
            if note is not None:
                mapping["progress_note"] = note
            if mapping:
                await r.hset(hkey, mapping=mapping)
        finally:
            if hasattr(r, "close"):
                await r.close()

