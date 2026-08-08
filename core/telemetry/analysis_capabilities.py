"""Stable names for analyses enabled by detected telemetry, not device brands."""

from __future__ import annotations


class AnalysisCapabilities:
    HEART_RATE = "heart_rate_analysis"
    HRV = "hrv_analysis"
    OXYGEN = "oxygen_analysis"
    MERGE = "time_merge"
    RECOVERY = "recovery_analysis"
    AI = "ai_summary"
    PDF = "pdf_report"
    LONGITUDINAL = "longitudinal_analysis"

