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

    # App commands defined in Cogs are automatically registered by discord.py.


async def setup(bot: commands.Bot):
    await bot.add_cog(PingCog(bot))
