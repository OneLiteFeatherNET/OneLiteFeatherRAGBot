from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Dict, Any
import os
import tempfile
import subprocess
import requests
import logging

from .base import IngestionSource, IngestItem
from .filesystem import FilesystemSource, DEFAULT_EXTS


@dataclass
class GitRepoSource(IngestionSource):
    repo_url: str
    branch: Optional[str] = None
    exts: List[str] | None = None
    token: Optional[str] = None
    workdir: Optional[Path] = None

    def stream(self) -> Iterable[IngestItem]:
        log = logging.getLogger(__name__)
        tmpdir_ctx = tempfile.TemporaryDirectory() if self.workdir is None else None
        root = self.workdir or Path(tmpdir_ctx.name)  # type: ignore[union-attr]
        repo_name = self.repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        dest = root / repo_name
        env = os.environ.copy()
        if self.token:
            # For GitHub, a simple way is to use token in URL if https
            if self.repo_url.startswith("https://") and "@" not in self.repo_url:
                self.repo_url = self.repo_url.replace("https://", f"https://{self.token}:x-oauth-basic@")
        if not dest.exists():
            log.info("Cloning repository: %s", self.repo_url)
            args = ["git", "clone", "--depth", "1"]
            if self.branch:
                args += ["--branch", self.branch]
            args += [self.repo_url, str(dest)]
            subprocess.run(args, check=True, env=env)

        fs = FilesystemSource(repo_root=dest, repo_url=self._public_repo_url(), exts=self.exts or DEFAULT_EXTS)
        yield from fs.stream()

        if tmpdir_ctx is not None:
            tmpdir_ctx.cleanup()

    def _public_repo_url(self) -> str:
        # Strip token from URL for metadata
        if "@" in self.repo_url:
            prefix, rest = self.repo_url.split("@", 1)
            if rest.startswith("github.com"):
                return "https://" + rest
        return self.repo_url


@dataclass
class GitHubOrgSource(IngestionSource):
    org: str
    visibility: str = "all"  # all|public|private
    include_archived: bool = False
    topics: List[str] | None = None
    exts: List[str] | None = None
    branch: Optional[str] = None
    token: Optional[str] = None

    def stream(self) -> Iterable[IngestItem]:
        for repo_url in self._list_repo_urls():
            yield from GitRepoSource(
                repo_url=repo_url,
                branch=self.branch,
                exts=self.exts or DEFAULT_EXTS,
                token=self.token,
            ).stream()

    def _list_repo_urls(self) -> List[str]:
        log = logging.getLogger(__name__)
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        urls: List[str] = []
        page = 1
        while True:
            params = {"per_page": 100, "page": page, "type": self.visibility}
            r = requests.get(f"https://api.github.com/orgs/{self.org}/repos", headers=headers, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            for repo in data:
                if not self.include_archived and repo.get("archived"):
                    continue
                if self.topics:
                    repo_topics = repo.get("topics") or []
                    if not set(self.topics).issubset(set(repo_topics)):
                        continue
                clone_url = repo.get("clone_url")
                if clone_url:
                    urls.append(clone_url)
            page += 1
        log.info("Discovered %d repos in org=%s", len(urls), self.org)
        return urls


@dataclass
class GitHubIssuesSource(IngestionSource):
    """Stream GitHub issues (optionally with comments) of a repository as IngestItems.

    repo_url: public HTTPS repo URL, e.g. https://github.com/ORG/REPO
    state: all|open|closed (default: all)
    labels: optional list of labels to filter by (subset)
    include_comments: include issue comments in the text
    token: optional GitHub token; if None uses env GITHUB_TOKEN when present
    """

    repo_url: str
    state: str = "all"
    labels: Optional[List[str]] = None
    include_comments: bool = True
    token: Optional[str] = None

    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/vnd.github+json"}
        tok = self.token or os.environ.get("GITHUB_TOKEN")
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        return h

    def _owner_repo(self) -> tuple[str, str]:
        # Parse https://github.com/owner/repo[.git]
        parts = self.repo_url.rstrip("/").split("/")
        owner, repo = parts[-2], parts[-1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        return owner, repo

    def _list_issues(self) -> List[Dict[str, Any]]:
        owner, repo = self._owner_repo()
        params: Dict[str, Any] = {"state": self.state or "all", "per_page": 100}
        if self.labels:
            params["labels"] = ",".join(self.labels)
        out: List[Dict[str, Any]] = []
        page = 1
        while True:
            params["page"] = page
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/issues",
                headers=self._headers(),
                params=params,
                timeout=60,
            )
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            for it in data:
                # Exclude pull requests (GH returns them in issues API when 'pull_request' key exists)
                if "pull_request" in it:
                    continue
                out.append(it)
            page += 1
        return out

    def _list_comments(self, number: int) -> List[Dict[str, Any]]:
        if not self.include_comments:
            return []
        owner, repo = self._owner_repo()
        out: List[Dict[str, Any]] = []
        page = 1
        while True:
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments",
                headers=self._headers(),
                params={"per_page": 100, "page": page},
                timeout=60,
            )
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            out.extend(data)
            page += 1
        return out

    def stream(self) -> Iterable[IngestItem]:
        log = logging.getLogger(__name__)
        issues = self._list_issues()
        owner, repo = self._owner_repo()
        repo_display = f"https://github.com/{owner}/{repo}"
        for iss in issues:
            number = int(iss.get("number"))
            title = iss.get("title") or ""
            body = iss.get("body") or ""
            html_url = iss.get("html_url") or f"{repo_display}/issues/{number}"
            labels = [lb.get("name") for lb in (iss.get("labels") or []) if lb and isinstance(lb, dict)]
            state = iss.get("state") or ""
            # Fetch comments if enabled
            comments_text = ""
            if self.include_comments and int(iss.get("comments") or 0) > 0:
                try:
                    comments = self._list_comments(number)
                    if comments:
                        parts: List[str] = ["\n\n--- Kommentare ---"]
                        for c in comments:
                            au = (c.get("user") or {}).get("login") or ""
                            tx = c.get("body") or ""
                            parts.append(f"[ {au} ]\n{tx}")
                        comments_text = "\n\n".join(parts)
                except Exception:
                    pass
            text = f"{title}\n\n{body}{comments_text}"
            checksum = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
            doc_id = f"{repo_display}#issue-{number}"
            metadata = {
                "repo": repo_display,
                "issue_number": number,
                "title": title,
                "state": state,
                "labels": labels,
                "source_url": html_url,
            }
            yield IngestItem(doc_id=doc_id, text=text, metadata=metadata, checksum=checksum)
