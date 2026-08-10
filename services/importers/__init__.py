"""Telemetry source adapters exposed through the importer registry."""

from services.importers.registry import get_importer

__all__ = ["get_importer"]
