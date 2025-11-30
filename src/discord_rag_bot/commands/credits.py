from __future__ import annotations

import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..infrastructure.permissions import require_admin
from ..infrastructure.credits import (
    get_usage,
    set_user_limit,
    clear_user_limit,
    add_unlimited_role,
    remove_unlimited_role,
    list_unlimited_roles,
)


class CreditCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    credits = app_commands.Group(name="credits", description="Admin: Credits Limits & Rollen verwalten")

    @credits.command(name="stats", description="Zeigt globale Nutzung und Cap des aktuellen Zeitraums")
    @require_admin()
    async def stats(self, interaction: discord.Interaction) -> None:
        # Show global usage; we need a user id for get_usage, reuse caller
        _, global_used = await asyncio.to_thread(get_usage, int(interaction.user.id))
        from ..config import settings
        cap = int(getattr(settings, "credit_global_cap", 0))
        await interaction.response.send_message(
            f"🌐 Global genutzt: {global_used} / Cap: {cap}", ephemeral=True
        )

    @credits.command(name="show", description="Zeigt die Nutzung und Limits eines Nutzers")
    @require_admin()
    async def show(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
        target = user or interaction.user
        user_used, global_used = await asyncio.to_thread(get_usage, int(target.id))
        from ..config import settings
        cap = int(getattr(settings, "credit_global_cap", 0))
        await interaction.response.send_message(
            f"👤 <@{target.id}> genutzt: {user_used}\n🌐 Global: {global_used}/{cap}", ephemeral=True
        )

    @credits.command(name="set-user-limit", description="Setzt ein benutzerbezogenes monatliches Limit (überschreibt Ränge)")
    @require_admin()
    async def set_user_limit_cmd(self, interaction: discord.Interaction, user: discord.Member, limit: int) -> None:
        await asyncio.to_thread(set_user_limit, int(user.id), int(limit))
        await interaction.response.send_message(
            f"✅ Limit für <@{user.id}> gesetzt auf {limit}", ephemeral=True
        )

    @credits.command(name="clear-user-limit", description="Entfernt das benutzerbezogene Limit (Rangregeln greifen wieder)")
    @require_admin()
    async def clear_user_limit_cmd(self, interaction: discord.Interaction, user: discord.Member) -> None:
        await asyncio.to_thread(clear_user_limit, int(user.id))
        await interaction.response.send_message(
            f"✅ Benutzerlimit für <@{user.id}> entfernt", ephemeral=True
        )

    @credits.command(name="add-unlimited-role", description="Fügt eine Rolle als 'unendlich' hinzu (per-user Limit entfällt)")
    @require_admin()
    async def add_unlimited_role_cmd(self, interaction: discord.Interaction, role: discord.Role) -> None:
        guild_id = interaction.guild.id if interaction.guild else None
        await asyncio.to_thread(add_unlimited_role, int(role.id), str(role.name or ""), int(guild_id) if guild_id else None)
        await interaction.response.send_message(
            f"✅ Rolle '{role.name}' ({role.id}) als unendlich registriert", ephemeral=True
        )

    @credits.command(name="remove-unlimited-role", description="Entfernt eine Rolle aus der 'unendlich' Liste")
    @require_admin()
    async def remove_unlimited_role_cmd(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await asyncio.to_thread(remove_unlimited_role, int(role.id))
        await interaction.response.send_message(
            f"✅ Rolle '{role.name}' ({role.id}) entfernt", ephemeral=True
        )

    @credits.command(name="list-unlimited-roles", description="Listet Rollen mit 'unendlich'-Status auf")
    @require_admin()
    async def list_unlimited_roles_cmd(self, interaction: discord.Interaction) -> None:
        rows = await asyncio.to_thread(list_unlimited_roles)
        if not rows:
            await interaction.response.send_message("(leer)", ephemeral=True)
            return
        lines = ["Unendliche Rollen:"]
        for rid, name, gid in rows:
            lines.append(f"- {name or '(ohne Namen)'} ({rid}) guild={gid or '-'}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CreditCommands(bot))

