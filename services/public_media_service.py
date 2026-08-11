"""Read-only, fail-closed public presentation of curated Content Studio media."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from database_postgres import db
from services.generated_media_service import resolve_media_path


logger = logging.getLogger(__name__)
PUBLIC_MEDIA_TYPES = {"image", "video"}
PUBLIC_STATUSES = {"approved", "published"}
PUBLIC_MIME_TYPES = {
    "image": {"image/avif", "image/jpeg", "image/png", "image/webp"},
    "video": {"video/mp4", "video/webm"},
}
PUBLIC_ROLE_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_RESOLUTION_RETRY_AT = 0.0


def _resolve_public_media_record(
    role: str, locale: str, media_type: str | None = None
) -> dict[str, Any] | None:
    """Return metadata for one explicitly curated public role, or ``None``.

    The role mapping is intentionally separate from generated media records. A
    record must remain final and approved/published at read time; changing its
    lifecycle status immediately removes it from the public surface.
    """
    if (
        not role
        or len(role) > 128
        or not PUBLIC_ROLE_PATTERN.fullmatch(role)
        or (media_type and media_type not in PUBLIC_MEDIA_TYPES)
    ):
        return None

    global _RESOLUTION_RETRY_AT
    if time.monotonic() < _RESOLUTION_RETRY_AT:
        return None

    connection = None
    cursor = None
    try:
        connection = db()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                asset.role, asset.alt_text_en, asset.alt_text_pl,
                media.id, media.media_type, media.mime_type, media.file_path,
                media.width, media.height,
                poster.id, poster.mime_type AS poster_mime_type
            FROM public_media_assets AS asset
            JOIN generated_media AS media ON media.id = asset.media_id
            LEFT JOIN generated_media AS poster ON poster.id = asset.poster_media_id
                AND poster.status IN ('approved', 'published')
                AND poster.is_final = TRUE
            WHERE asset.role = %s
              AND media.status IN ('approved', 'published')
              AND media.is_final = TRUE
              AND media.media_type IN ('image', 'video')
              AND (%s IS NULL OR media.media_type = %s)
            """,
            (role, media_type, media_type),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [description[0] for description in cursor.description]
        result = dict(zip(columns, row))
        if result.get("mime_type") not in PUBLIC_MIME_TYPES[result["media_type"]]:
            return None
        result["alt_text"] = result["alt_text_pl"] if locale == "pl" else result["alt_text_en"]
        return result
    except Exception:
        # A missing migration or unavailable media database must never take a
        # public page down or expose uncurated fallback records.
        _RESOLUTION_RETRY_AT = time.monotonic() + 30
        logger.warning("Public media role resolution failed for %s; using the static fallback", role)
        return None
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def resolve_public_media(
    role: str, locale: str, media_type: str | None = None
) -> dict[str, Any] | None:
    """Return a safe public presentation object without private storage metadata."""
    record = _resolve_public_media_record(role, locale, media_type)
    if record is None:
        return None
    return {
        "media_type": record["media_type"],
        "mime_type": record["mime_type"],
        "width": record["width"],
        "height": record["height"],
        "alt_text": record["alt_text"],
        "poster_available": (
            record.get("poster_id") is not None
            and record.get("poster_mime_type") in PUBLIC_MIME_TYPES["image"]
        ),
    }


def resolve_public_media_file(role: str, locale: str) -> tuple[Path, str] | None:
    """Resolve an eligible local file for the public route only."""
    record = _resolve_public_media_record(role, locale)
    if record is None:
        return None
    try:
        path = resolve_media_path(record["file_path"])
    except ValueError:
        return None
    return path, record["mime_type"]
