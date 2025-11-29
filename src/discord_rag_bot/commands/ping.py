from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class PingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Ping-Pong Check")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pong!", ephemeral=True)

    async def cog_load(self) -> None:  # type: ignore[override]
        self.bot.tree.add_command(self.ping)

    async def cog_unload(self) -> None:  # type: ignore[override]
        try:
            self.bot.tree.remove_command(self.ping.name, type=self.ping.type)
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(PingCog(bot))

