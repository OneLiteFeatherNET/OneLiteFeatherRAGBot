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
        # cache allowed guild ids for restrictive sync/checks
        self._allowed_guild_ids = set(int(g) for g in (getattr(settings, "guild_ids", []) or []))

    def _app_command_guild_check(self, interaction: discord.Interaction) -> bool:
        # Restrictive: when guild_ids configured, only allow those guilds
        if not self._allowed_guild_ids:
            return True
        return interaction.guild_id in self._allowed_guild_ids

    async def setup_hook(self):
        await load_all_cogs(self)
        # Apply restrictive guild check to all slash commands
        self.tree.add_check(self._app_command_guild_check)
        # Guild-specific sync if configured; otherwise global
        if self._allowed_guild_ids:
            for gid in self._allowed_guild_ids:
                guild_obj = discord.Object(id=int(gid))
                self.tree.copy_global_to(guild=guild_obj)
                await self.tree.sync(guild=guild_obj)
        else:
            await self.tree.sync()

    async def on_ready(self):
        status = getattr(settings, "bot_status", None)
        if status:
            await self.change_presence(activity=discord.Game(name=status))
