"""Translation dictionary service for CoreLabTech.

UI, JavaScript and PDF reports use the same JSON dictionaries. English is the
required fallback catalog, while every supported locale must keep the same keys.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import g, has_request_context

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "pl")
LOCALE_COOKIE_NAME = "corelabtech_locale"
TRANSLATIONS_DIRECTORY = Path(__file__).resolve().parents[1] / "translations"


def normalize_locale(value: str | None) -> str:
    """Return a supported short locale code."""

    if not value:
        return DEFAULT_LOCALE

    normalized = str(value).strip().lower().replace("_", "-").split("-")[0]
    return normalized if normalized in SUPPORTED_LOCALES else DEFAULT_LOCALE


def _catalog_signature() -> tuple[tuple[str, int, int], ...]:
    """Return a small signature that changes when dictionary files change."""

    signature = []
    for locale in SUPPORTED_LOCALES:
        path = TRANSLATIONS_DIRECTORY / f"{locale}.json"
        stat = path.stat()
        signature.append((locale, stat.st_mtime_ns, stat.st_size))

    return tuple(signature)


@lru_cache(maxsize=8)
def _load_translation_catalogs(
    _signature: tuple[tuple[str, int, int], ...],
) -> dict[str, dict[str, str]]:
    """Load all supported JSON dictionaries from disk."""

    catalogs: dict[str, dict[str, str]] = {}

    for locale in SUPPORTED_LOCALES:
        path = TRANSLATIONS_DIRECTORY / f"{locale}.json"
        with path.open("r", encoding="utf-8") as file:
            loaded = json.load(file)

        catalogs[locale] = {
            str(key): str(value)
            for key, value in loaded.items()
        }

    return catalogs


def translations() -> dict[str, dict[str, str]]:
    """Return cached translation catalogs."""

    return _load_translation_catalogs(_catalog_signature())


def locale_from_request(request) -> str:
    """Resolve locale from query string, cookie or Accept-Language."""

    query_locale = normalize_locale(request.args.get("lang"))
    if request.args.get("lang") and query_locale in SUPPORTED_LOCALES:
        return query_locale

    cookie_locale = normalize_locale(request.cookies.get(LOCALE_COOKIE_NAME))
    if cookie_locale in SUPPORTED_LOCALES and request.cookies.get(
        LOCALE_COOKIE_NAME
    ):
        return cookie_locale

    return normalize_locale(request.accept_languages.best_match(SUPPORTED_LOCALES))


def current_locale() -> str:
    """Return the active request locale, falling back to English."""

    if has_request_context():
        return normalize_locale(getattr(g, "locale", DEFAULT_LOCALE))

    return DEFAULT_LOCALE


def translate(key: str, **params: Any) -> str:
    """Translate one key with English fallback and optional format params."""

    catalogs = translations()
    locale = current_locale()
    text = (
        catalogs.get(locale, {}).get(key)
        or catalogs[DEFAULT_LOCALE].get(key)
        or key
    )

    if params:
        try:
            return text.format(**params)
        except (KeyError, ValueError):
            return text

    return text


def catalog_for(locale: str | None) -> dict[str, str]:
    """Return a frontend catalog merged over English fallback."""

    catalogs = translations()
    normalized = normalize_locale(locale)
    return {
        **catalogs[DEFAULT_LOCALE],
        **catalogs.get(normalized, {}),
    }
