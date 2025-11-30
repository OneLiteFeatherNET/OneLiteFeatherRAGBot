from __future__ import annotations

import logging
import os


def setup_logging(default_level: str | None = None) -> None:
    level_name = (default_level or os.getenv("APP_LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

