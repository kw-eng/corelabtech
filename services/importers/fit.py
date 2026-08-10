"""FIT importer for wearable telemetry files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.telemetry.contract import canonicalize_telemetry_rows
from services.fit_parser import parse_fit_file


class FitTelemetryImporter:
    """Adapt the FIT parser to the telemetry importer contract."""

    import_type = "fit"
    parser_version = "fit-v5"

    def import_data(self, path: str | Path) -> list[dict[str, Any]]:
        return canonicalize_telemetry_rows(parse_fit_file(path))
