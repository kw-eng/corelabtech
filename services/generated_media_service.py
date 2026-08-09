from __future__ import annotations

import mimetypes
from dataclasses import replace
from html import escape as escape_xml
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from database_postgres import db


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_MEDIA_TYPES = {
    "image",
    "video",
    "thumbnail",
    "social",
}

ALLOWED_STATUSES = {
    "draft",
    "generated",
    "approved",
    "published",
    "archived",
    "failed",
}


@dataclass(frozen=True)
class GeneratedMediaInput:
    media_type: str
    scene_id: str
    character_id: str
    version: str
    ai_provider: str
    prompt: str
    file_path: str

    negative_prompt: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    status: str = "generated"
    is_final: bool = False
    notes: str | None = None
    created_by: int | None = None


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
    columns = [
        description[0]
        for description in cursor.description
    ]

    return dict(zip(columns, row))


def normalize_relative_path(file_path: str) -> str:
    """
    Normalizuje ścieżkę do formatu względnego, niezależnego od systemu.

    Dozwolone:
        assets/athlete/generated/images/home/file.webp

    Niedozwolone:
        D:\\project\\assets\\...
        /opt/corelabtech/assets/...
        ../../secret.txt
    """
    if not file_path or not file_path.strip():
        raise ValueError("file_path is required")

    raw_path = file_path.strip().replace("\\", "/")
    path = Path(raw_path)

    if path.is_absolute():
        raise ValueError(
            "file_path must be relative to the project root"
        )

    if ".." in path.parts:
        raise ValueError(
            "file_path cannot contain '..'"
        )

    normalized = path.as_posix().lstrip("/")

    if not normalized.startswith("assets/"):
        raise ValueError(
            "file_path must point to the assets directory"
        )

    return normalized


def resolve_media_path(file_path: str) -> Path:
    """
    Zwraca bezpieczną ścieżkę absolutną do pliku.
    """
    normalized = normalize_relative_path(file_path)

    project_root = PROJECT_ROOT.resolve()
    absolute_path = (project_root / normalized).resolve()

    try:
        absolute_path.relative_to(project_root)
    except ValueError as error:
        raise ValueError(
            "Resolved path is outside the project root"
        ) from error

    return absolute_path


def validate_media_input(data: GeneratedMediaInput) -> None:
    if data.media_type not in ALLOWED_MEDIA_TYPES:
        raise ValueError(
            f"Unsupported media_type: {data.media_type}"
        )

    if data.status not in ALLOWED_STATUSES:
        raise ValueError(
            f"Unsupported status: {data.status}"
        )

    if not data.scene_id.strip():
        raise ValueError("scene_id is required")

    if not data.character_id.strip():
        raise ValueError("character_id is required")

    if not data.version.strip():
        raise ValueError("version is required")

    if not data.ai_provider.strip():
        raise ValueError("ai_provider is required")

    if not data.prompt.strip():
        raise ValueError("prompt is required")

    if data.width is not None and data.width <= 0:
        raise ValueError("width must be greater than zero")

    if data.height is not None and data.height <= 0:
        raise ValueError("height must be greater than zero")

    if (
        data.duration_seconds is not None
        and data.duration_seconds < 0
    ):
        raise ValueError(
            "duration_seconds cannot be negative"
        )


def register_generated_media(
    data: GeneratedMediaInput,
) -> dict[str, Any]:
    validate_media_input(data)

    file_path = normalize_relative_path(data.file_path)
    absolute_path = resolve_media_path(file_path)
    file_name = absolute_path.name

    detected_mime_type, _ = mimetypes.guess_type(file_name)

    mime_type = (
        data.mime_type
        or detected_mime_type
        or "application/octet-stream"
    )

    file_size_bytes = (
        absolute_path.stat().st_size
        if absolute_path.is_file()
        else None
    )

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO generated_media (
                media_type,
                scene_id,
                character_id,
                version,
                ai_provider,
                prompt,
                negative_prompt,
                file_path,
                file_name,
                mime_type,
                width,
                height,
                duration_seconds,
                file_size_bytes,
                status,
                is_final,
                notes,
                created_by
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            RETURNING
                id,
                media_type,
                scene_id,
                character_id,
                version,
                ai_provider,
                prompt,
                negative_prompt,
                file_path,
                file_name,
                mime_type,
                width,
                height,
                duration_seconds,
                file_size_bytes,
                status,
                is_final,
                notes,
                created_by,
                created_at,
                updated_at
            """,
            (
                data.media_type,
                data.scene_id.strip(),
                data.character_id.strip(),
                data.version.strip(),
                data.ai_provider.strip(),
                data.prompt.strip(),
                (
                    data.negative_prompt.strip()
                    if data.negative_prompt
                    else None
                ),
                file_path,
                file_name,
                mime_type,
                data.width,
                data.height,
                data.duration_seconds,
                file_size_bytes,
                data.status,
                data.is_final,
                (
                    data.notes.strip()
                    if data.notes
                    else None
                ),
                data.created_by,
            ),
        )

        row = cursor.fetchone()
        result = _row_to_dict(cursor, row)

        connection.commit()
        return result

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def create_mock_generated_media(
    data: GeneratedMediaInput,
    *,
    generation_job_id: str,
) -> dict[str, Any]:
    """Create a clearly labelled deterministic development artifact and register it."""

    artifact_dir = PROJECT_ROOT / "assets" / "athlete" / "generated" / "development"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    filename = f"mock-{generation_job_id}.svg"
    artifact_path = artifact_dir / filename
    artifact_path.write_text(
        """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1600\" height=\"900\" viewBox=\"0 0 1600 900\">
<rect width=\"1600\" height=\"900\" fill=\"#061526\"/><rect x=\"80\" y=\"80\" width=\"1440\" height=\"740\" rx=\"32\" fill=\"#0b263d\" stroke=\"#22d3ee\" stroke-width=\"3\"/>
<text x=\"160\" y=\"280\" fill=\"#67e8f9\" font-family=\"Arial\" font-size=\"72\" font-weight=\"bold\">CoreLabTech</text>
<text x=\"160\" y=\"390\" fill=\"#ffffff\" font-family=\"Arial\" font-size=\"46\">Mock Provider Development Artifact</text>
<text x=\"160\" y=\"500\" fill=\"#cbd5e1\" font-family=\"Arial\" font-size=\"32\">Character: %s</text>
<text x=\"160\" y=\"555\" fill=\"#cbd5e1\" font-family=\"Arial\" font-size=\"32\">Scene: %s</text>
<text x=\"160\" y=\"670\" fill=\"#94a3b8\" font-family=\"Arial\" font-size=\"26\">This deterministic artifact is not AI-generated media.</text></svg>"""
        % (escape_xml(data.character_id), escape_xml(data.scene_id)),
        encoding="utf-8",
    )
    try:
        return register_generated_media(
            replace(
                data,
                media_type="image",
                version=f"mock-{generation_job_id[:8]}",
                file_path=f"assets/athlete/generated/development/{filename}",
                mime_type="image/svg+xml",
                width=1600,
                height=900,
                notes=f"Mock Provider development artifact; generation job {generation_job_id}",
            )
        )
    except Exception:
        artifact_path.unlink(missing_ok=True)
        raise


def list_generated_media(
    *,
    media_type: str | None = None,
    scene_id: str | None = None,
    character_id: str | None = None,
    status: str | None = None,
    is_final: bool | None = None,
    created_by: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if media_type and media_type not in ALLOWED_MEDIA_TYPES:
        raise ValueError(
            f"Unsupported media_type: {media_type}"
        )

    if status and status not in ALLOWED_STATUSES:
        raise ValueError(
            f"Unsupported status: {status}"
        )

    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    conditions: list[str] = []
    params: list[Any] = []

    if media_type:
        conditions.append("media_type = %s")
        params.append(media_type)

    if scene_id:
        conditions.append("scene_id = %s")
        params.append(scene_id)

    if character_id:
        conditions.append("character_id = %s")
        params.append(character_id)

    if status:
        conditions.append("status = %s")
        params.append(status)

    if is_final is not None:
        conditions.append("is_final = %s")
        params.append(is_final)

    if created_by is not None:
        conditions.append("created_by = %s")
        params.append(created_by)

    where_clause = ""

    if conditions:
        where_clause = (
            "WHERE " + " AND ".join(conditions)
        )

    params.extend([limit, offset])

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            f"""
            SELECT
                id,
                media_type,
                scene_id,
                character_id,
                version,
                ai_provider,
                prompt,
                negative_prompt,
                file_path,
                file_name,
                mime_type,
                width,
                height,
                duration_seconds,
                file_size_bytes,
                status,
                is_final,
                notes,
                created_by,
                created_at,
                updated_at
            FROM generated_media
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            OFFSET %s
            """,
            tuple(params),
        )

        columns = [
            description[0]
            for description in cursor.description
        ]

        return [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

    finally:
        cursor.close()
        connection.close()


def get_generated_media(
    media_id: int,
    *,
    created_by: int | None = None,
) -> dict[str, Any] | None:
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                id,
                media_type,
                scene_id,
                character_id,
                version,
                ai_provider,
                prompt,
                negative_prompt,
                file_path,
                file_name,
                mime_type,
                width,
                height,
                duration_seconds,
                file_size_bytes,
                status,
                is_final,
                notes,
                created_by,
                created_at,
                updated_at
            FROM generated_media
            WHERE id = %s
              AND (%s IS NULL OR created_by = %s)
            """,
            (media_id, created_by, created_by),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return _row_to_dict(cursor, row)

    finally:
        cursor.close()
        connection.close()


def update_generated_media_status(
    media_id: int,
    *,
    status: str,
    is_final: bool | None = None,
    notes: str | None = None,
    created_by: int | None = None,
) -> dict[str, Any] | None:
    if status not in ALLOWED_STATUSES:
        raise ValueError(
            f"Unsupported status: {status}"
        )

    assignments = [
        "status = %s",
        "updated_at = NOW()",
    ]
    params: list[Any] = [status]

    if is_final is not None:
        assignments.append("is_final = %s")
        params.append(is_final)

    if notes is not None:
        assignments.append("notes = %s")
        params.append(notes.strip() or None)

    params.extend([media_id, created_by, created_by])

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            f"""
            UPDATE generated_media
            SET {", ".join(assignments)}
            WHERE id = %s
              AND (%s IS NULL OR created_by = %s)
            RETURNING
                id,
                media_type,
                scene_id,
                character_id,
                version,
                ai_provider,
                file_path,
                file_name,
                status,
                is_final,
                notes,
                created_at,
                updated_at
            """,
            tuple(params),
        )

        row = cursor.fetchone()

        if row is None:
            connection.rollback()
            return None

        result = _row_to_dict(cursor, row)
        connection.commit()

        return result

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()
