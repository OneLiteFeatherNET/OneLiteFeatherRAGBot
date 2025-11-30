from __future__ import annotations

from typing import Optional

from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

FALLBACK_LANGUAGE = "English"

LANGUAGE_MAP = {
    "de": "Deutsch",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "pl": "Polski",
}


def get_language_hint(text: str) -> Optional[str]:
    if not text:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    try:
        code = detect(cleaned)
        return LANGUAGE_MAP.get(code, cleaned)
    except Exception:
        return None
