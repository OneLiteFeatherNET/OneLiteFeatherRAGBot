from __future__ import annotations

from pathlib import Path
from ..config import settings


def _prompt_path() -> Path:
    root = Path(getattr(settings, "etl_staging_dir", ".staging"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "system_prompt.txt"


def save_system_prompt(text: str | None) -> None:
    p = _prompt_path()
    if text is None or text.strip() == "":
        if p.exists():
            p.unlink(missing_ok=True)
        return
    p.write_text(text, encoding="utf-8")


def load_system_prompt() -> str | None:
    p = _prompt_path()
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


# Scoped prompts (channel overrides guild, guild overrides global)
def _prompts_root() -> Path:
    root = Path(getattr(settings, "etl_staging_dir", ".staging")) / "prompts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_prompt_global(text: str | None) -> None:
    root = _prompts_root()
    p = root / "global.txt"
    if not text:
        p.unlink(missing_ok=True)
        return
    p.write_text(text, encoding="utf-8")


def save_prompt_guild(guild_id: int, text: str | None) -> None:
    root = _prompts_root()
    p = root / f"guild-{guild_id}.txt"
    if not text:
        p.unlink(missing_ok=True)
        return
    p.write_text(text, encoding="utf-8")


def save_prompt_channel(channel_id: int, text: str | None) -> None:
    root = _prompts_root()
    p = root / f"channel-{channel_id}.txt"
    if not text:
        p.unlink(missing_ok=True)
        return
    p.write_text(text, encoding="utf-8")


def load_prompt_effective(guild_id: int | None, channel_id: int | None) -> str | None:
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
