from __future__ import annotations

import asyncio
import importlib
import inspect
import pkgutil
from types import ModuleType
from typing import Iterable

from discord.ext import commands


async def _maybe_await(result):
    if inspect.isawaitable(result):
        return await result
    return result


async def load_all_cogs(bot: commands.Bot, package: str = "discord_rag_bot.commands") -> int:
    """Dynamically discover and load all command modules under the package.

    Each module should define an async `setup(bot)` function that adds its Cog.
    """
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

