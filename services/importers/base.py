"""Stable interface for transforming an external file into telemetry rows."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class TelemetryImporter(Protocol):
    """Adapter implemented by every supported telemetry file source."""

    import_type: str
    parser_version: str

    def import_data(self, path: str | Path) -> list[dict[str, Any]]:
        """Parse a source file into the canonical row vocabulary."""
