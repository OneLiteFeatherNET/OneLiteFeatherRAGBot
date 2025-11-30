from __future__ import annotations

import discord
from discord import app_commands

from ..config import settings


def is_admin_member(member: discord.Member) -> bool:
    # Always allow guild administrators
    if member.guild_permissions.administrator:
        return True
    # Check configured roles by ID or name
    role_ids = set(int(r) for r in (getattr(settings, "admin_role_ids", []) or []))
    role_names = set((getattr(settings, "admin_role_names", []) or []))
    if not role_ids and not role_names:
        return False
    for r in member.roles:
        if r.id in role_ids:
            return True
        if r.name in role_names:
            return True
    return False


def require_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        user = interaction.user
        if isinstance(user, discord.Member):
            return is_admin_member(user)
        return False

    return app_commands.check(predicate)

