from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Dict, Any
import base64
import hashlib
import requests
import logging

from .base import IngestionSource, IngestItem
from github import Github
from .filesystem import FilesystemSource, DEFAULT_EXTS


@dataclass
class GitRepoSource(IngestionSource):
    repo_url: str
    branch: Optional[str] = None
    exts: List[str] | None = None
    token: Optional[str] = None
    workdir: Optional[Path] = None  # no-op for API mode; kept for compatibility

    def stream(self) -> Iterable[IngestItem]:
        log = logging.getLogger(__name__)
        gh = Github(login_or_token=self.token) if self.token else Github()
        # Parse owner/repo from URL
        parts = self.repo_url.rstrip("/").split("/")
        owner, repo_name = parts[-2], parts[-1].removesuffix(".git")
        repo = gh.get_repo(f"{owner}/{repo_name}")
        ref = self.branch or repo.default_branch
        # List tree recursively
        tree = repo.get_git_tree(ref, recursive=True)
        wanted_exts = set(self.exts or DEFAULT_EXTS)
        for entry in getattr(tree, "tree", []):
            if getattr(entry, "type", "blob") != "blob":
                continue
            path = entry.path
            suffix = "." + path.split(".")[-1] if "." in path else ""
            if wanted_exts and suffix not in wanted_exts:
                continue
            try:
                blob = repo.get_git_blob(entry.sha)
                content = base64.b64decode(blob.content or b"")
                text = content.decode("utf-8", errors="ignore")
            except Exception:
                continue
            meta_repo = repo.html_url
            source_url = f"{meta_repo}/blob/{ref}/{path}"
            doc_id = f"{meta_repo}@{path}"
            checksum = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
            metadata = {"repo": meta_repo, "file_path": path, "source_url": source_url}
            yield IngestItem(doc_id=doc_id, text=text, metadata=metadata, checksum=checksum)


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
        gh = Github(login_or_token=self.token) if self.token else Github()
        org = gh.get_organization(self.org)
        repos = org.get_repos(type=self.visibility)
        urls: List[str] = []
        for repo in repos:
            try:
                if not self.include_archived and bool(getattr(repo, "archived", False)):
                    continue
                if self.topics:
                    topics = set(repo.get_topics() or [])
                    if not set(self.topics).issubset(topics):
                        continue
                urls.append(str(repo.clone_url))
            except Exception:
                continue
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

    def stream(self) -> Iterable[IngestItem]:
        log = logging.getLogger(__name__)
        gh = Github(login_or_token=self.token) if self.token else Github()
        # Parse owner/repo from URL
        parts = self.repo_url.rstrip("/").split("/")
        owner, repo_name = parts[-2], parts[-1].removesuffix(".git")
        repo = gh.get_repo(f"{owner}/{repo_name}")
        issues = repo.get_issues(state=self.state or "all", labels=self.labels or None)
        for issue in issues:
            try:
                if getattr(issue, "pull_request", None):
                    # PyGithub hides PRs in get_issues by default; extra safety
                    continue
            except Exception:
                pass
            title = issue.title or ""
            body = issue.body or ""
            comments_text = ""
            if self.include_comments and issue.comments > 0:
                try:
                    parts_c: List[str] = []
                    for c in issue.get_comments():
                        au = getattr(getattr(c, "user", None), "login", "") or ""
                        tx = c.body or ""
                        parts_c.append(f"[ {au} ]\n{tx}")
                    if parts_c:
                        comments_text = "\n\n--- Kommentare ---\n" + "\n\n".join(parts_c)
                except Exception:
                    pass
            text = f"{title}\n\n{body}{comments_text}"
            checksum = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
            html_url = issue.html_url
            doc_id = html_url  # stable unique id per issue
            metadata = {
                "repo": repo.html_url,
                "issue_number": int(issue.number),
                "title": title,
                "state": issue.state,
                "labels": [lb.name for lb in (issue.labels or [])],
                "source_url": html_url,
            }
            yield IngestItem(doc_id=doc_id, text=text, metadata=metadata, checksum=checksum)
