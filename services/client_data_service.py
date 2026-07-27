"""Portable client export for access and data portability requests."""

from __future__ import annotations

import json
import zipfile
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any


CLIENT_TABLES = {
    "profile": ("users", "user_id"),
    "sessions": ("full_sessions", "user_id"),
    "phase_measurements": ("tests", "user_id"),
    "fit_imports": ("fit_imports", "user_id"),
    "fit_timeline": ("fit_data", "user_id"),
    "csv_imports": ("csv_imports", "user_id"),
    "csv_timeline": ("csv_data", "user_id"),
    "merge_jobs": ("merge_jobs", "user_id"),
    "merged_timeline": ("merged_data", "user_id"),
    "analyses": ("ai_results", "user_id"),
    "session_features": ("session_features", "user_id"),
    "daily_baselines": ("daily_baselines", "user_id"),
    "hrv_imports": ("hrv_imports", "user_id"),
    "hrv_intervals": ("hrv_intervals", "user_id"),
    "consents": ("consent_records", "client_id"),
}


def build_client_export(cursor, *, client_id: str) -> BytesIO:
    """Build a ZIP containing JSON files from client-owned tables."""

    files: dict[str, list[dict[str, Any]]] = {}

    for export_name, (table_name, owner_column) in CLIENT_TABLES.items():
        if not table_exists(cursor, table_name):
            continue

        cursor.execute(
            f"""
            SELECT *
            FROM {table_name}
            WHERE {owner_column} = %s
            ORDER BY 1
            """,
            (client_id,),
        )
        columns = [description[0] for description in cursor.description]
        files[export_name] = [
            {
                column: json_value(value)
                for column, value in zip(columns, row)
            }
            for row in cursor.fetchall()
        ]

    archive = BytesIO()

    with zipfile.ZipFile(
        archive,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zip_file:
        manifest = {
            "format": "CoreLabTech client export",
            "version": "1.0",
            "client_id": client_id,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "files": sorted(f"{name}.json" for name in files),
        }
        zip_file.writestr(
            "manifest.json",
            json.dumps(manifest, indent=2),
        )

        for name, rows in files.items():
            zip_file.writestr(
                f"{name}.json",
                json.dumps(rows, indent=2, ensure_ascii=True),
            )

    archive.seek(0)
    return archive


def table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT to_regclass(%s)",
        (f"public.{table_name}",),
    )
    return cursor.fetchone()[0] is not None


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, memoryview):
        return bytes(value).hex()
    if isinstance(value, bytes):
        return value.hex()
    return value
