from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BuildInfo:
    version: str | None
    commit: str | None
    date: str | None


def _pkg_version() -> str | None:
    try:
        import importlib.metadata as im  # py3.8+
        return im.version("discord-rag-bot")
    except Exception:
        return None


def get_build_info() -> BuildInfo:
    version = os.getenv("APP_BUILD_VERSION") or _pkg_version()
    commit = os.getenv("APP_BUILD_COMMIT")
    date = os.getenv("APP_BUILD_DATE")
    return BuildInfo(version=version, commit=commit, date=date)

