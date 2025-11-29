from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional
import os
import tempfile
import subprocess
import requests

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
        return urls
