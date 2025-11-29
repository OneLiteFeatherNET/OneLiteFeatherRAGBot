from __future__ import annotations

import discord
from discord.ext import commands

from ..commands.loader import load_all_cogs
from .services import BotServices


class RagBot(commands.Bot):
    def __init__(self, services: BotServices):
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)
        self.services = services

    async def setup_hook(self):
        await load_all_cogs(self)
        await self.tree.sync()

