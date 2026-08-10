"""Checkme-compatible pulse-oximeter CSV importer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.telemetry.contract import canonicalize_telemetry_rows
from services.csv_parser import parse_csv_file


class CheckmeCsvImporter:
    """Adapt the existing CSV parser to the telemetry importer contract."""

    import_type = "csv"
    parser_version = "csv-v2"

    def import_data(self, path: str | Path) -> list[dict[str, Any]]:
        return canonicalize_telemetry_rows(parse_csv_file(path))
