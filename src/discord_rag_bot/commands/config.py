from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..infrastructure.config_store import (
    save_system_prompt,
    load_system_prompt,
    save_prompt_global,
    save_prompt_guild,
    save_prompt_channel,
    load_prompt_effective,
)
from ..infrastructure.ai import build_ai_provider
from ..infrastructure.config_store import migrate_prompts_files_to_db


class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="config", description="Configure bot behavior (admin)")

    @staticmethod
    def admin_check():
        async def predicate(interaction: discord.Interaction) -> bool:
            if isinstance(interaction.user, discord.Member):
                return interaction.user.guild_permissions.administrator
            return False
        return app_commands.check(predicate)

    @group.command(name="system_prompt_get", description="Get current system prompt")
    @admin_check.__func__()
    async def system_prompt_get(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        p = load_system_prompt()
        if not p:
            await interaction.followup.send("No system prompt set.", ephemeral=True)
        else:
            await interaction.followup.send(f"Current system prompt:\n```\n{p}\n```", ephemeral=True)

    @group.command(name="system_prompt_set", description="Set system prompt for LLM")
    @admin_check.__func__()
    @app_commands.describe(text="New system prompt text", scope="Scope: global|guild|channel")
    async def system_prompt_set(self, interaction: discord.Interaction, text: str, scope: str = "global"):
        await interaction.response.defer(ephemeral=True)
        scope = scope.lower().strip()
        if scope == "channel":
            if not interaction.channel:
                await interaction.followup.send("No channel context.", ephemeral=True)
                return
            save_prompt_channel(interaction.channel.id, text)
        elif scope == "guild":
            if not interaction.guild:
                await interaction.followup.send("No guild context.", ephemeral=True)
                return
            save_prompt_guild(interaction.guild.id, text)
        else:
            save_prompt_global(text)
        # reconfigure LLM globally
        ai = build_ai_provider()
        ai.configure_global()
        self.bot.services.rag.ai_provider = ai  # type: ignore[attr-defined]
        await interaction.followup.send(f"System prompt updated for scope '{scope}' and LLM reconfigured.", ephemeral=True)

    @group.command(name="system_prompt_clear", description="Clear system prompt")
    @admin_check.__func__()
    @app_commands.describe(scope="Scope: global|guild|channel")
    async def system_prompt_clear(self, interaction: discord.Interaction, scope: str = "global"):
        await interaction.response.defer(ephemeral=True)
        scope = scope.lower().strip()
        if scope == "channel":
            if not interaction.channel:
                await interaction.followup.send("No channel context.", ephemeral=True)
                return
            save_prompt_channel(interaction.channel.id, None)
        elif scope == "guild":
            if not interaction.guild:
                await interaction.followup.send("No guild context.", ephemeral=True)
                return
            save_prompt_guild(interaction.guild.id, None)
        else:
            save_prompt_global(None)
        ai = build_ai_provider()
        ai.configure_global()
        self.bot.services.rag.ai_provider = ai  # type: ignore[attr-defined]
        await interaction.followup.send(f"System prompt cleared for scope '{scope}'.", ephemeral=True)

    @group.command(name="system_prompt_effective", description="Show effective system prompt for this channel")
    @admin_check.__func__()
    async def system_prompt_effective(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        text = load_prompt_effective(interaction.guild_id, interaction.channel_id)
        if not text:
            await interaction.followup.send("No channel/guild override; using global/ENV (if any).", ephemeral=True)
        else:
            await interaction.followup.send(f"Effective prompt for this channel:\n```\n{text}\n```", ephemeral=True)

    @group.command(name="migrate_prompts_to_db", description="Migrate .staging prompts into DB settings (admin)")
    @admin_check.__func__()
    @app_commands.describe(delete_files="Delete files after successful migration")
    async def migrate_prompts_to_db(self, interaction: discord.Interaction, delete_files: bool = True):
        await interaction.response.defer(ephemeral=True)
        stats = migrate_prompts_files_to_db(delete_files=delete_files)
        # Reconfigure LLM (prompt might change)
        ai = build_ai_provider()
        ai.configure_global()
        self.bot.services.rag.ai_provider = ai  # type: ignore[attr-defined]
        await interaction.followup.send(
            f"Migration done: global={stats.get('global',0)} guild={stats.get('guild',0)} channel={stats.get('channel',0)} deleted={stats.get('deleted', False)}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    cog = ConfigCog(bot)
    await bot.add_cog(cog)
    # Ensure the grouped commands are registered
    try:
        bot.tree.add_command(ConfigCog.group)
    except Exception:
        pass
