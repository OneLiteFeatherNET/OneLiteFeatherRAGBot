from __future__ import annotations

from .config import settings
from .bot.startup import build_bot


def main() -> None:
    bot = build_bot()
    bot.run(settings.discord_token)
