from __future__ import annotations

from .config import settings
from .bot.startup import build_bot
from rag_core.logging import setup_logging


def main() -> None:
    setup_logging()
    bot = build_bot()
    bot.run(settings.discord_token)
