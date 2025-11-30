from __future__ import annotations

from typing import Optional, Literal

import discord
from discord import app_commands
from discord.ext import commands

from ..util.text import clip_discord_message
from ..infrastructure.permissions import is_admin_member


class MemoryCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    memory = app_commands.Group(name="memory", description="Zeige oder lösche dein Konversations‑Gedächtnis")

    @memory.command(name="show", description="Zeigt die gespeicherten Konversationsdaten (Zusammenfassung + letzte Schritte)")
    async def show(
        self,
        interaction: discord.Interaction,
        scope: Literal["channel", "all"] = "channel",
        user: Optional[discord.Member] = None,
        limit: int = 8,
        ephemeral: bool = True,
    ) -> None:
        target = user or interaction.user
        if user and user.id != interaction.user.id:
            # Only admins may view other users' memory
            if not (isinstance(interaction.user, discord.Member) and is_admin_member(interaction.user)):
                await interaction.response.send_message("❌ Nur Admins dürfen die Erinnerung anderer Nutzer anzeigen.", ephemeral=True)
                return

        channel_id = interaction.channel.id if (scope == "channel" and hasattr(interaction.channel, "id")) else None
        try:
            mem = self.bot.services.memory.get_context(user_id=int(target.id), channel_id=channel_id, limit=int(limit))  # type: ignore[attr-defined]
        except Exception as e:
            await interaction.response.send_message(f"❌ Konnte Memory nicht laden: {e}", ephemeral=True)
            return

        lines: list[str] = []
        lines.append(f"🧠 Memory für <@{target.id}> — Scope: {scope}")
        if mem.summary:
            lines.append("\nZusammenfassung:")
            lines.append(mem.summary.strip())
        if mem.recent:
            lines.append("\nLetzte Schritte:")
            for r, c in mem.recent[-limit:]:
                prefix = "User" if r == "user" else "Bot"
                lines.append(f"- {prefix}: {c[:400]}")
        if len(lines) == 1:
            lines.append("(Keine Einträge)")
        text = clip_discord_message("\n".join(lines))

        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(text, ephemeral=ephemeral)

    @memory.command(name="clear", description="Löscht gespeicherte Konversationsdaten")
    async def clear(
        self,
        interaction: discord.Interaction,
        scope: Literal["channel", "all"] = "channel",
        user: Optional[discord.Member] = None,
        confirm: bool = False,
        ephemeral: bool = True,
    ) -> None:
        # Determine target user and permissions
        target = user or interaction.user
        is_self = (target.id == interaction.user.id)
        if not is_self:
            if not (isinstance(interaction.user, discord.Member) and is_admin_member(interaction.user)):
                await interaction.response.send_message("❌ Nur Admins dürfen die Erinnerung anderer Nutzer löschen.", ephemeral=True)
                return

        if not confirm:
            await interaction.response.send_message(
                "⚠️ Bitte bestätige mit `confirm:true` um zu löschen.", ephemeral=True
            )
            return

        channel_id = interaction.channel.id if (scope == "channel" and hasattr(interaction.channel, "id")) else None

        try:
            count = self.bot.services.memory.clear(user_id=int(target.id), channel_id=channel_id, scope=scope)  # type: ignore[attr-defined]
        except Exception as e:
            await interaction.response.send_message(f"❌ Löschen fehlgeschlagen: {e}", ephemeral=True)
            return

        msg = f"✅ Memory von <@{target.id}> gelöscht (Scope: {scope}, Einträge: {count})."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(msg, ephemeral=ephemeral)


async def setup(bot: commands.Bot):
    await bot.add_cog(MemoryCommands(bot))

