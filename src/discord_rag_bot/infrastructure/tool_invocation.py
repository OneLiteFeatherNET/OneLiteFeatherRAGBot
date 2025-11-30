from __future__ import annotations

import json
import re
from typing import Optional, Tuple, Any, Dict

from .permissions import is_admin_member


_FENCE_RE = re.compile(r"```(tool|json)\s*\n(\{[\s\S]*?\})\s*```", re.MULTILINE)


def extract_tool_call(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Extract a single tool call from a fenced JSON block.

    Expected formats inside the code fence:
      {"tool": "queue.web.url", "payload": {"urls": ["https://..."]}}
    or
      {"name": "queue.web.url", "payload": {...}}
    """
    if not text:
        return None
    m = _FENCE_RE.search(text)
    if not m:
        return None
    body = m.group(2)
    try:
        obj = json.loads(body)
        name = obj.get("tool") or obj.get("name")
        payload = obj.get("payload") or {}
        if not isinstance(name, str) or not isinstance(payload, dict):
            return None
        return name, payload
    except Exception:
        return None


def can_run_tools_for_user(user) -> bool:
    """Only Discord admins or configured admin roles may trigger tools."""
    try:
        import discord  # type: ignore
        if isinstance(user, discord.Member):
            # Guild administrators or configured admin roles
            return bool(user.guild_permissions.administrator or is_admin_member(user))
    except Exception:
        pass
    return False

