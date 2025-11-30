from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from rag_core.tools.base import Tool, ToolResult
from rag_core.orm.session import session_scope
from rag_core.orm.models import RagChecksum
from ..config import settings


def _group_repos_from_checksums() -> List[Tuple[str, int, str | None]]:
    """Return list of (repo_url, doc_count, last_updated) based on doc_id prefix."""
    out: Dict[str, Tuple[int, str | None]] = {}
    with session_scope(settings.db) as sess:  # type: ignore
        rows = sess.query(RagChecksum.doc_id, RagChecksum.updated_at).all()
        for doc_id, updated_at in rows:
            doc_id = str(doc_id)
            repo = doc_id.split("@", 1)[0]
            cnt, last = out.get(repo, (0, None))
            cnt += 1
            last_iso = str(updated_at) if updated_at is not None else None
            # simple max by string iso ordering
            if last is None or (last_iso and last_iso > last):
                last = last_iso
            out[repo] = (cnt, last)
    # sort by last desc
    items = [(r, c, t) for r, (c, t) in out.items()]
    items.sort(key=lambda x: (x[2] or ""), reverse=True)
    return items


class ListKnownReposTool(Tool):
    name = "repos.list"
    description = "List known repositories from the index. payload: { limit?: number }"

    def run(self, payload: Dict[str, Any]) -> ToolResult:
        limit = int(payload.get("limit") or 10)
        items = _group_repos_from_checksums()[:limit]
        if not items:
            return ToolResult(content="no repositories found in index", raw={"repos": []})
        lines = ["Known repositories (latest first):"]
        for repo, count, last in items:
            lines.append(f"- {repo} (docs: {count}, last: {last or '-'})")
        return ToolResult(content="\n".join(lines), raw={"repos": items})


class RepoReindexTool(Tool):
    name = "repos.reindex"
    description = "Re-index a known repository. payload: { repo: string, branch?: string, exts?: string[], chunk_size?: number, chunk_overlap?: number }"

    def __init__(self, enqueue_callable) -> None:
        self._enqueue = enqueue_callable

    def run(self, payload: Dict[str, Any]) -> ToolResult:
        repo = str(payload.get("repo") or "").strip()
        if not repo:
            return ToolResult(content="repo is required")
        cfg: Dict[str, Any] = {
            "sources": [
                {"type": "github_repo", "repo": repo}
            ]
        }
        if payload.get("branch"):
            cfg["sources"][0]["branch"] = str(payload["branch"])  # type: ignore[index]
        if payload.get("exts"):
            cfg["sources"][0]["exts"] = list(payload["exts"])  # type: ignore[index]
        if payload.get("chunk_size"):
            cfg["chunk_size"] = int(payload["chunk_size"])  # type: ignore[index]
            cfg["chunk_overlap"] = int(payload.get("chunk_overlap") or 200)  # type: ignore[index]

        job_id = __import__("asyncio").run(self._enqueue("ingest", cfg))
        return ToolResult(content=f"queued reindex job #{job_id} for {repo}", raw={"job_id": job_id, "repo": repo})

