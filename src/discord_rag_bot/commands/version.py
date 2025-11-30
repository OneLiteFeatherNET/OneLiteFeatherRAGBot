from __future__ import annotations

import platform
from discord import app_commands
from discord.ext import commands
import discord

from ..infrastructure.build_info import get_build_info


class VersionCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="version", description="Show bot version and build info")
    async def version(self, interaction: discord.Interaction) -> None:
        bi = get_build_info()
        py = platform.python_version()
        lines = ["🤖 Bot version info:"]
        lines.append(f"- version: {bi.version or '(unknown)'}")
        if bi.commit:
            lines.append(f"- commit: {bi.commit[:7] if len(bi.commit or '')>7 else bi.commit}")
        if bi.date:
            lines.append(f"- build: {bi.date}")
        lines.append(f"- python: {py}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VersionCommands(bot))

