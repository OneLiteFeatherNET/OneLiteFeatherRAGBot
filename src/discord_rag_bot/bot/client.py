from __future__ import annotations

import discord
from discord.ext import commands

from ..commands.loader import load_all_cogs
from ..config import settings
from .services import BotServices


class RagBot(commands.Bot):
    def __init__(self, services: BotServices):
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)
        self.services = services

    async def setup_hook(self):
        await load_all_cogs(self)
        # Guild-specific sync if configured; otherwise global
        if getattr(settings, "guild_ids", None):
            for gid in settings.guild_ids:
                guild_obj = discord.Object(id=int(gid))
                self.tree.copy_global_to(guild=guild_obj)
                await self.tree.sync(guild=guild_obj)
        else:
            await self.tree.sync()

    async def on_ready(self):
        status = getattr(settings, "bot_status", None)
        if status:
            await self.change_presence(activity=discord.Game(name=status))
