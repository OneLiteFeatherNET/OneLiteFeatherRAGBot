from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Optional

from discord.ext import commands


async def _maybe_await(result):
    if inspect.isawaitable(result):
        return await result
    return result


async def load_all_listeners(bot: commands.Bot, package: str = "discord_rag_bot.listeners") -> int:
    pkg = importlib.import_module(package)
    count = 0
    for m in pkgutil.iter_modules(pkg.__path__):
        name = m.name
        if name in {"__init__", "loader"}:
            continue
        mod = importlib.import_module(f"{package}.{name}")
        setup_fn = getattr(mod, "setup", None)
        if setup_fn and callable(setup_fn):
            await _maybe_await(setup_fn(bot))
            count += 1
    return count

