from __future__ import annotations

import discord
from discord.ext import commands

from ..commands.loader import load_all_cogs
from ..config import settings
from .services import BotServices


class RagBot(commands.Bot):
    def __init__(self, services: BotServices):
        intents = discord.Intents.default()
        if getattr(settings, "enable_message_content_intent", False):
            intents.message_content = True
        # Disable text-prefix commands by using mention-only prefix
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.services = services
        # cache allowed guild ids for restrictive sync/checks
        self._allowed_guild_ids = set(int(g) for g in (getattr(settings, "guild_ids", []) or []))

    async def setup_hook(self):
        await load_all_cogs(self)
        # Guild-specific sync if configured; otherwise global
        if self._allowed_guild_ids:
            # Copy all global commands into each allowed guild
            guild_objs = [discord.Object(id=int(g)) for g in self._allowed_guild_ids]
            for gobj in guild_objs:
                self.tree.copy_global_to(guild=gobj)
            # Clear global and sync to remove any global registrations
            self.tree.clear_commands(guild=None)
            await self.tree.sync(guild=None)
            # Now sync per guild
            for gobj in guild_objs:
                await self.tree.sync(guild=gobj)
        else:
            await self.tree.sync()

    async def on_message(self, message: discord.Message):
        """Do not process legacy prefix commands; only our listeners run."""
        # Intentionally do not call process_commands to avoid treating first word as command
        return

    async def on_ready(self):
        status = getattr(settings, "bot_status", None)
        if status:
            await self.change_presence(activity=discord.Game(name=status))
