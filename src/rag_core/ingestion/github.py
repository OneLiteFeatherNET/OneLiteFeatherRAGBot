from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable, List, Optional, Dict, Any
import base64
import hashlib
import requests
import subprocess
import shutil
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
        token = self.token or os.getenv("GITHUB_TOKEN")
        gh = Github(login_or_token=token) if token else Github()
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
            # Commit metadata (last commit for this path on ref) – optional for rate‑limit control
            commit_sha = None
            commit_date = None
            commit_author = None
            commit_message = None
            if (os.getenv("APP_GITHUB_COMMIT_METADATA", "true").lower() == "true"):
                try:
                    commits = repo.get_commits(path=path, sha=ref)
                    last = commits[0] if commits.totalCount > 0 else None  # type: ignore[attr-defined]
                    if last is not None:
                        commit_sha = getattr(last, "sha", None)
                        try:
                            commit_date = getattr(getattr(last, "commit", None), "author", None).date.isoformat()  # type: ignore[attr-defined]
                        except Exception:
                            commit_date = None
                        try:
                            commit_author = getattr(getattr(last, "author", None), "login", None)
                        except Exception:
                            commit_author = None
                        try:
                            commit_message = getattr(getattr(last, "commit", None), "message", None)
                        except Exception:
                            commit_message = None
                except Exception:
                    pass
            checksum = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
            metadata = {
                "repo": meta_repo,
                "file_path": path,
                "source_url": source_url,
                "branch": ref,
                "commit_sha": commit_sha,
                "commit_date": commit_date,
                "commit_author": commit_author,
                "commit_message": commit_message,
            }
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
        token = self.token or os.getenv("GITHUB_TOKEN")
        gh = Github(login_or_token=token) if token else Github()
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
        token = self.token or os.getenv("GITHUB_TOKEN")
        gh = Github(login_or_token=token) if token else Github()
        # Parse owner/repo from URL
        parts = self.repo_url.rstrip("/").split("/")
        owner, repo_name = parts[-2], parts[-1].removesuffix(".git")
        repo = gh.get_repo(f"{owner}/{repo_name}")
        issues = repo.get_issues(state=self.state or "all", labels=list(self.labels or []))
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


@dataclass
class GitRepoLocalSource(IngestionSource):
    """Clone a GitHub repository locally and stream files from disk.

    Reduces API usage and allows indexing large repos reliably.
    """

    repo_url: str
    branch: Optional[str] = None
    exts: List[str] | None = None
    workdir: Optional[Path] = None  # base directory for clones (default: $APP_ETL_STAGING_DIR/repos)
    shallow: bool = True
    fetch_depth: int = 50

    def _safe_dir(self) -> Path:
        # Derive owner-repo from URL
        parts = self.repo_url.rstrip("/").split("/")
        owner, repo_name = parts[-2], parts[-1].removesuffix(".git")
        base = self.workdir or Path(os.getenv("APP_ETL_STAGING_DIR", ".staging")) / "repos"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{owner}-{repo_name}"

    def _run_git(self, args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=str(cwd) if cwd else None, check=True, text=True, capture_output=True)

    def _ensure_clone(self, dest: Path, branch: Optional[str]) -> str:
        if not shutil.which("git"):
            raise RuntimeError("git binary not found in PATH; required for local clone mode")
        if not dest.exists():
            args = ["clone", "--no-tags", "--single-branch"]
            if branch:
                args += ["--branch", branch]
            if self.shallow and self.fetch_depth > 0:
                args += ["--depth", str(int(self.fetch_depth))]
            args += [self.repo_url, str(dest)]
            self._run_git(args)
        else:
            # fetch + checkout + pull
            try:
                self._run_git(["fetch", "--all", "--prune"], cwd=dest)
            except Exception:
                pass
            if branch:
                self._run_git(["checkout", branch], cwd=dest)
            if self.shallow and self.fetch_depth > 0:
                try:
                    self._run_git(["pull", "--ff-only", "--depth", str(int(self.fetch_depth))], cwd=dest)
                except Exception:
                    self._run_git(["pull", "--ff-only"], cwd=dest)
            else:
                self._run_git(["pull", "--ff-only"], cwd=dest)
        # Determine current branch
        try:
            out = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=dest).stdout.strip()
            return out or (branch or "main")
        except Exception:
            return branch or "main"

    def stream(self) -> Iterable[IngestItem]:
        log = logging.getLogger(__name__)
        clone_dir = self._safe_dir()
        ref = self._ensure_clone(clone_dir, self.branch)
        wanted_exts = set(self.exts or DEFAULT_EXTS)
        # Guess HTML base URL from repo_url
        html_base = self.repo_url.rstrip("/").removesuffix(".git")
        for p in clone_dir.rglob("*"):
            if not p.is_file():
                continue
            if ".git" in p.parts:
                continue
            if wanted_exts and p.suffix not in wanted_exts:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(p.relative_to(clone_dir)).replace("\\", "/")
            # commit meta for path
            commit_sha = None
            commit_date = None
            commit_author = None
            commit_message = None
            try:
                fmt = "%H\x1f%an\x1f%ad\x1f%s"
                out = self._run_git(["log", "-n", "1", "--date=iso", f"--pretty={fmt}", "--", rel], cwd=clone_dir).stdout.strip()
                if out:
                    parts = out.split("\x1f")
                    if len(parts) >= 4:
                        commit_sha, commit_author, commit_date, commit_message = parts[0], parts[1], parts[2], parts[3]
            except Exception:
                pass
            metadata = {
                "repo": html_base,
                "file_path": rel,
                "source_url": f"{html_base}/blob/{ref}/{rel}",
                "branch": ref,
                "commit_sha": commit_sha,
                "commit_date": commit_date,
                "commit_author": commit_author,
                "commit_message": commit_message,
            }
            doc_id = f"{html_base}@{rel}"
            checksum = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
            yield IngestItem(doc_id=doc_id, text=text, metadata=metadata, checksum=checksum)
