"""Central registry for supported telemetry file importers."""

from __future__ import annotations

from services.importers.base import TelemetryImporter
from services.importers.checkme_csv import CheckmeCsvImporter
from services.importers.fit import FitTelemetryImporter
from services.importers.apple_health import AppleHealthXmlImporter
from services.importers.health_connect import HealthConnectJsonImporter
from services.importers.polar_csv import PolarCsvImporter


IMPORTERS: dict[str, TelemetryImporter] = {
    "csv": CheckmeCsvImporter(),
    "fit": FitTelemetryImporter(),
    "apple_health_xml": AppleHealthXmlImporter(),
    "health_connect_json": HealthConnectJsonImporter(),
    "polar_csv": PolarCsvImporter(),
}


def get_importer(import_type: str) -> TelemetryImporter:
    """Return a registered importer or fail before any database work begins."""

    try:
        return IMPORTERS[import_type]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported telemetry import type: {import_type}"
        ) from exc
