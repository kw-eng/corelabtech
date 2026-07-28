"""Longitudinal session-series analytics for wellness dashboards and reports."""

from __future__ import annotations

from typing import Any

from database_postgres import db


def get_user_series_trends(
    *,
    user_id: str,
    protocol_id: int | None = None,
    trend_limit: int = 25,
) -> dict[str, Any]:
    """Return longitudinal AI trend data for one client."""

    connection = db()
    cursor = connection.cursor()

    try:
        if protocol_id is None:
            cursor.execute(
                """
                SELECT protocol_id
                FROM full_sessions
                WHERE user_id = %s
                  AND completed = 1
                  AND session_id NOT LIKE 'PIPELINE_VALIDATION_%%'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            protocol_row = cursor.fetchone()
            protocol_id = protocol_row[0] if protocol_row else None

        cursor.execute(
            """
            SELECT
                session_id,
                overall_score,
                data_quality_score,
                anomaly_detected,
                summary,
                features_json,
                result_json,
                created_at
            FROM (
                SELECT *
                FROM (
                    SELECT DISTINCT ON (ar.session_id)
                        ar.session_id,
                        ar.overall_score,
                        ar.data_quality_score,
                        ar.anomaly_detected,
                        ar.summary,
                        ar.features_json,
                        ar.result_json,
                        ar.created_at,
                        ar.ai_result_id
                    FROM ai_results ar
                    JOIN full_sessions fs
                        ON fs.session_id = ar.session_id
                    WHERE fs.user_id = %s
                      AND fs.protocol_id = %s
                      AND ar.session_id NOT LIKE 'PIPELINE_VALIDATION_%%'
                    ORDER BY
                        ar.session_id,
                        ar.created_at DESC,
                        ar.ai_result_id DESC
                ) latest_per_session
                ORDER BY created_at DESC, ai_result_id DESC
                LIMIT %s
            ) limited_series
            ORDER BY created_at ASC, ai_result_id ASC
            """,
            (user_id, protocol_id, trend_limit),
        )
        analysis_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT COUNT(DISTINCT session_id)
            FROM full_sessions
            WHERE user_id = %s
              AND protocol_id = %s
              AND session_id NOT LIKE 'PIPELINE_VALIDATION_%%'
            """,
            (user_id, protocol_id),
        )
        session_count_row = cursor.fetchone()
        session_count = session_count_row[0] if session_count_row else 0

        cursor.execute(
            """
            SELECT code, name, target_ata
            FROM protocols
            WHERE protocol_id = %s
            """,
            (protocol_id,),
        )
        selected_protocol_row = cursor.fetchone()

    finally:
        cursor.close()
        connection.close()

    analyses, aggregates = build_series_analyses(analysis_rows)
    selected_protocol = (
        {
            "protocol_id": protocol_id,
            "code": selected_protocol_row[0],
            "name": selected_protocol_row[1],
            "target_ata": selected_protocol_row[2],
        }
        if selected_protocol_row
        else None
    )

    return {
        "status": "ok",
        "user_id": user_id,
        "protocol": selected_protocol,
        "records": len(analyses),
        "series_limit": trend_limit,
        "session_count": session_count,
        "avg_score": average_or_none(aggregates["scores"]),
        "latest_score": aggregates["scores"][-1]
        if aggregates["scores"]
        else None,
        "avg_data_quality": average_or_none(aggregates["data_quality_values"]),
        "avg_coverage": average_or_none(aggregates["coverage_values"]),
        "latest_data_quality": (
            aggregates["data_quality_values"][-1]
            if aggregates["data_quality_values"]
            else None
        ),
        "avg_match_rate": average_or_none(aggregates["match_rate_values"]),
        "avg_synchronized_samples": average_or_none(
            aggregates["synchronized_sample_values"]
        ),
        "avg_spo2": average_or_none(aggregates["spo2_values"]),
        "avg_pulse": average_or_none(aggregates["pulse_values"]),
        "avg_hrv": average_or_none(aggregates["hrv_values"]),
        "anomaly_count": sum(
            1 for row in analyses if row["anomaly_detected"]
        ),
        "flagged_session_count": sum(
            1 for row in analyses if row["session_flagged"]
        ),
        "trend_direction": calculate_trend_direction(aggregates["scores"]),
        "data_quality_trend": calculate_trend_direction(
            aggregates["data_quality_values"]
        ),
        "first_last_comparison": compare_session_windows(analyses),
        "data_quality_engine": build_data_quality_engine_summary(analyses),
        "wellness_interpretation": build_series_wellness_interpretation(
            analyses,
            aggregates["scores"],
            aggregates["data_quality_values"],
        ),
        "analyses": analyses,
        "timeline": analyses,
    }


def build_series_analyses(rows) -> tuple[list[dict[str, Any]], dict[str, list[float]]]:
    analyses = []
    aggregates = {
        "scores": [],
        "hrv_values": [],
        "spo2_values": [],
        "pulse_values": [],
        "data_quality_values": [],
        "coverage_values": [],
        "match_rate_values": [],
        "synchronized_sample_values": [],
    }

    for row in rows:
        features = row[5] or {}
        result_json = row[6] or {}
        wellness_flags = result_json.get("wellness_flags") or {}

        score = row[1]
        avg_hrv = pick_feature(features, "avg_hrv")
        avg_spo2 = pick_feature(features, "avg_spo2", "avg_csv_spo2")
        avg_pulse = pick_feature(features, "avg_pulse", "avg_csv_pulse")
        data_quality_score = row[2]
        match_rate = pick_feature(features, "match_rate")
        samples_total = pick_feature(features, "samples_total")
        samples_synchronized = pick_feature(features, "samples_synchronized")
        coverage_percent = calculate_coverage_percent(
            samples_total,
            samples_synchronized,
        )
        quality_warnings = (
            result_json.get("quality_warnings")
            or features.get("quality_warnings")
            or []
        )
        if not isinstance(quality_warnings, list):
            quality_warnings = []

        append_numeric(aggregates["scores"], score)
        append_numeric(aggregates["hrv_values"], avg_hrv)
        append_numeric(aggregates["spo2_values"], avg_spo2)
        append_numeric(aggregates["pulse_values"], avg_pulse)
        append_numeric(aggregates["data_quality_values"], data_quality_score)
        append_numeric(aggregates["coverage_values"], coverage_percent)
        append_numeric(aggregates["match_rate_values"], match_rate)
        append_numeric(
            aggregates["synchronized_sample_values"],
            samples_synchronized,
        )

        analyses.append({
            "session_id": row[0],
            "overall_score": score,
            "data_quality_score": data_quality_score,
            "anomaly_detected": bool(row[3]),
            "session_flagged": bool(
                result_json.get("session_flagged", row[3])
            ),
            "wellness_status": result_json.get("wellness_status"),
            "elevated_load": bool(
                wellness_flags.get("elevated_load", False)
            ),
            "oxygenation_drop": bool(
                wellness_flags.get("oxygenation_drop", False)
            ),
            "sensor_alignment_warning": bool(
                wellness_flags.get("sensor_alignment_warning", False)
            ),
            "summary": row[4],
            "avg_spo2": avg_spo2,
            "avg_pulse": avg_pulse,
            "avg_hrv": avg_hrv,
            "match_rate": match_rate,
            "coverage_percent": coverage_percent,
            "samples_total": samples_total,
            "samples_synchronized": samples_synchronized,
            "missing_samples": calculate_missing_samples(
                samples_total,
                samples_synchronized,
            ),
            "quality_warnings": quality_warnings,
            "quality_warning_count": len(quality_warnings),
            "max_hr_pulse_difference": pick_feature(
                features,
                "max_hr_pulse_difference",
            ),
            "min_spo2": pick_feature(features, "min_spo2"),
            "created_at": row[7].isoformat() if row[7] else None,
        })

    return analyses, aggregates


def pick_feature(features: dict, *keys: str):
    for key in keys:
        value = features.get(key)

        if value is not None:
            return value

    return None


def append_numeric(values: list[float], value) -> None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return

    values.append(numeric)


def average_or_none(values: list[float]) -> float | None:
    if not values:
        return None

    return round(sum(values) / len(values), 2)


def calculate_missing_samples(samples_total, samples_synchronized) -> int | None:
    try:
        total = int(samples_total)
        synchronized = int(samples_synchronized)
    except (TypeError, ValueError):
        return None

    return max(0, total - synchronized)


def calculate_coverage_percent(samples_total, samples_synchronized) -> float | None:
    try:
        total = float(samples_total)
        synchronized = float(samples_synchronized)
    except (TypeError, ValueError):
        return None

    if total <= 0:
        return None

    return round(max(0, min(100, (synchronized / total) * 100)), 2)


def average_series_field(rows: list[dict], field: str) -> float | None:
    values = []

    for row in rows:
        append_numeric(values, row.get(field))

    return average_or_none(values)


def compare_session_windows(analyses: list[dict], window_size: int = 5) -> dict:
    if not analyses:
        return {
            "window_size": window_size,
            "available": False,
            "message": "No analyzed sessions available.",
        }

    first_window = analyses[:window_size]
    last_window = analyses[-window_size:]
    first_score = average_series_field(first_window, "overall_score")
    last_score = average_series_field(last_window, "overall_score")
    first_quality = average_series_field(first_window, "data_quality_score")
    last_quality = average_series_field(last_window, "data_quality_score")

    return {
        "window_size": window_size,
        "available": len(analyses) >= 2,
        "first_count": len(first_window),
        "last_count": len(last_window),
        "first_avg_score": first_score,
        "last_avg_score": last_score,
        "score_delta": calculate_delta(first_score, last_score),
        "first_avg_data_quality": first_quality,
        "last_avg_data_quality": last_quality,
        "data_quality_delta": calculate_delta(first_quality, last_quality),
    }


def calculate_delta(first, last) -> float | None:
    try:
        return round(float(last) - float(first), 2)
    except (TypeError, ValueError):
        return None


def build_data_quality_engine_summary(analyses: list[dict]) -> dict:
    warning_counts: dict[str, int] = {}

    for row in analyses:
        for warning in row.get("quality_warnings") or []:
            warning_counts[warning] = warning_counts.get(warning, 0) + 1

    total_missing_samples = sum(
        int(row.get("missing_samples") or 0)
        for row in analyses
    )

    return {
        "avg_quality_score": average_series_field(
            analyses,
            "data_quality_score",
        ),
        "avg_coverage": average_series_field(analyses, "coverage_percent"),
        "avg_sync_quality": average_series_field(analyses, "match_rate"),
        "total_missing_samples": total_missing_samples,
        "flagged_quality_sessions": sum(
            1 for row in analyses if row.get("quality_warnings")
        ),
        "sensor_gap_sessions": sum(
            1
            for row in analyses
            if any(
                warning in {
                    "missing_hrv_or_rr",
                    "missing_spo2",
                    "too_few_synchronized_samples",
                }
                for warning in row.get("quality_warnings") or []
            )
        ),
        "hr_pulse_mismatch_sessions": sum(
            1 for row in analyses if has_hr_pulse_mismatch(row)
        ),
        "spo2_warning_sessions": sum(
            1 for row in analyses if has_spo2_range_warning(row)
        ),
        "warning_counts": warning_counts,
        "explanation": (
            "Session Data Quality reflects synchronized sample coverage, sensor "
            "availability, HR/pulse alignment and SpO2 signal plausibility. It is "
            "a data-confidence indicator, not a health assessment."
        ),
    }


def has_hr_pulse_mismatch(row: dict) -> bool:
    if "sensor_alignment_warning" in (row.get("quality_warnings") or []):
        return True

    try:
        difference = float(row.get("max_hr_pulse_difference"))
    except (TypeError, ValueError):
        return False

    return difference > 10


def has_spo2_range_warning(row: dict) -> bool:
    warnings = row.get("quality_warnings") or []

    if row.get("oxygenation_drop") or "missing_spo2" in warnings:
        return True

    try:
        min_spo2 = float(row.get("min_spo2"))
    except (TypeError, ValueError):
        return False

    return min_spo2 < 90 or min_spo2 > 100


def build_series_wellness_interpretation(
    analyses: list[dict],
    scores: list[float],
    data_quality_values: list[float],
) -> str:
    if not analyses:
        return (
            "No analyzed session series is available yet. Run session analyses "
            "before interpreting longitudinal wellness trends."
        )

    trend = calculate_trend_direction(scores)
    quality_trend = calculate_trend_direction(data_quality_values)

    if not data_quality_values or average_or_none(data_quality_values) < 60:
        return (
            "This session series has limited data confidence. Review missing "
            "samples, synchronization quality and sensor warnings before using "
            "the trend for wellness coaching."
        )

    if trend == "improving":
        trend_text = "The wellness response trend is improving across the selected series."
    elif trend == "declining":
        trend_text = (
            "The wellness response trend is lower across the selected series. "
            "Operator review is recommended."
        )
    elif trend == "stable":
        trend_text = "The wellness response trend is stable across the selected series."
    else:
        trend_text = "More analyzed sessions are needed to establish a trend."

    if quality_trend == "declining":
        quality_text = (
            " Data quality is trending down, so interpretation should be more cautious."
        )
    else:
        quality_text = (
            " Interpretation should remain tied to the available data quality."
        )

    return trend_text + quality_text


def calculate_trend_direction(values: list[float]) -> str:
    if len(values) < 2:
        return "unknown"

    first = values[0]
    last = values[-1]
    delta = last - first

    if abs(delta) < 2:
        return "stable"

    return "improving" if delta > 0 else "declining"
