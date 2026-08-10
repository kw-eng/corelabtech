"""Synchronize FIT and CSV telemetry into one research timeline.

FIT data usually carries wearable heart-rate/HRV signals, while CSV data carries
pulse oximeter SpO2/pulse signals. This module matches those streams by nearest
timestamp and stores the merged timeline for analysis.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from core.telemetry.contract import SCHEMA_VERSION
from database_postgres import db
from services.hrv_pipeline import annotate_hrv_rmssd_timeline

from repositories.data_repository import (
    get_latest_completed_csv_import,
    get_latest_completed_fit_import,
    load_csv,
    load_fit,
)

from repositories.merge_repository import (
    complete_merge_job,
    create_merge_job,
    insert_merged_measurements,
)


MERGE_ALGORITHM = "nearest_timestamp"
DEFAULT_TOLERANCE_MS = 2500
TIME_OFFSET_CANDIDATE_HOURS = range(-12, 13)


class MergeError(Exception):
    """Base class for merge failures that routes can convert to JSON errors."""

    pass


class MergeInputMissingError(MergeError):
    """Raised when one side of the FIT/CSV timeline is missing or empty."""

    pass


@dataclass(frozen=True)
class MergeResult:
    """Summary returned after one completed merge job."""

    merge_id: int
    session_id: str
    user_id: str

    fit_import_id: int | None
    csv_import_id: int

    fit_records: int
    csv_records: int
    merged_records: int

    matched_records: int
    unmatched_records: int
    match_rate: float

    algorithm: str
    tolerance_ms: int
    fit_time_offset_hours: int
    mode: str

    def to_dict(self) -> dict:
        return asdict(self)


def merge_session_data(
    *,
    session_id: str,
    user_id: str | None = None,
    tolerance_ms: int = DEFAULT_TOLERANCE_MS,
) -> MergeResult:
    """Load latest completed imports, merge them and persist a merge job.

    The function owns the database transaction so callers get either a complete
    merge job with rows, or no partial merge state.
    """

    connection = db()
    cursor = connection.cursor()

    try:
        fit_import = get_latest_completed_fit_import(
            cursor,
            session_id=session_id,
        )

        csv_import = get_latest_completed_csv_import(
            cursor,
            session_id=session_id,
        )

        if not csv_import:
            raise MergeInputMissingError(
                "No completed CSV import found"
            )

        final_user_id = (
            user_id
            or (fit_import or {}).get("user_id")
            or csv_import.get("user_id")
            or session_id
        )

        csv_rows = load_csv(
            cursor,
            session_id=session_id,
            import_id=csv_import["id"],
        )

        if not csv_rows:
            raise MergeInputMissingError(
                "CSV import contains no measurements"
            )

        if fit_import:
            fit_rows = load_fit(
                cursor,
                session_id=session_id,
                import_id=fit_import["id"],
            )

            if not fit_rows:
                raise MergeInputMissingError(
                    "FIT import contains no measurements"
                )

            merged_rows = merge_fit_and_csv(
                fit_rows=fit_rows,
                csv_rows=csv_rows,
                tolerance_ms=tolerance_ms,
            )

            algorithm = MERGE_ALGORITHM
            mode = "fit_csv"
            fit_import_id = fit_import["id"]
            fit_records = len(fit_rows)
            fit_time_offset_hours = first_not_none(
                *[
                    row.get("fit_time_offset_hours")
                    for row in merged_rows
                ],
                0,
            )

        else:
            merged_rows = merge_csv_only(
                csv_rows=csv_rows,
            )

            algorithm = "csv_only"
            mode = "csv_only"
            fit_import_id = None
            fit_records = 0
            fit_time_offset_hours = 0

        merge_id = create_merge_job(
            cursor,
            session_id=session_id,
            user_id=final_user_id,
            fit_import_id=fit_import_id,
            csv_import_id=csv_import["id"],
            fit_records=fit_records,
            csv_records=len(csv_rows),
            algorithm=algorithm,
            tolerance_ms=tolerance_ms,
        )

        saved = insert_merged_measurements(
            cursor,
            merge_id=merge_id,
            session_id=session_id,
            user_id=final_user_id,
            rows=merged_rows,
        )

        matched = sum(
            1
            for row in merged_rows
            if row.get("synchronized") is True
        )

        unmatched = len(merged_rows) - matched

        match_rate = (
            round(matched / len(merged_rows) * 100, 2)
            if merged_rows
            else 0.0
        )

        complete_merge_job(
            cursor,
            merge_id=merge_id,
            merged_records=saved,
            notes=(
                f"mode={mode}; "
                f"fit_time_offset_hours={fit_time_offset_hours}; "
                f"tolerance_ms={tolerance_ms}; "
                f"matched_records={matched}; "
                f"match_rate={match_rate}"
            ),
            time_alignment_method=first_not_none(
                *[
                    row.get("time_alignment_method")
                    for row in merged_rows
                ],
            ),
            time_alignment_quality=first_not_none(
                *[
                    row.get("time_alignment_quality")
                    for row in merged_rows
                ],
            ),
        )

        connection.commit()

        return MergeResult(
            merge_id=merge_id,
            session_id=session_id,
            user_id=final_user_id,
            fit_import_id=fit_import_id,
            csv_import_id=csv_import["id"],
            fit_records=fit_records,
            csv_records=len(csv_rows),
            merged_records=saved,
            matched_records=matched,
            unmatched_records=unmatched,
            match_rate=match_rate,
            algorithm=algorithm,
            tolerance_ms=tolerance_ms,
            fit_time_offset_hours=fit_time_offset_hours,
            mode=mode,
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def merge_fit_and_csv(
    *,
    fit_rows: list[dict[str, Any]],
    csv_rows: list[dict[str, Any]],
    tolerance_ms: int,
) -> list[dict[str, Any]]:
    """Match CSV rows to the nearest FIT row within the tolerance window."""

    fit_df = pd.DataFrame(fit_rows)
    csv_df = pd.DataFrame(csv_rows)

    fit_df["fit_timestamp"] = pd.to_datetime(
        fit_df["timestamp"],
        errors="coerce",
    )
    fit_df["fit_timestamp_utc"] = pd.to_datetime(
        fit_df.get(
            "timestamp_utc",
            pd.Series(index=fit_df.index, dtype="object"),
        ),
        errors="coerce",
        utc=True,
    )

    csv_df["csv_timestamp"] = pd.to_datetime(
        csv_df["timestamp"],
        errors="coerce",
    )
    csv_df["csv_timestamp_utc"] = pd.to_datetime(
        csv_df.get(
            "timestamp_utc",
            pd.Series(index=csv_df.index, dtype="object"),
        ),
        errors="coerce",
        utc=True,
    )

    fit_df = (
        fit_df
        .dropna(subset=["fit_timestamp"])
        .sort_values("fit_timestamp")
    )

    csv_df = (
        csv_df
        .dropna(subset=["csv_timestamp"])
        .sort_values("csv_timestamp")
    )

    if fit_df.empty:
        raise MergeInputMissingError(
            "No valid FIT timestamps"
        )

    if csv_df.empty:
        raise MergeInputMissingError(
            "No valid CSV timestamps"
        )

    use_utc = (
        fit_df["fit_timestamp_utc"].notna().all()
        and csv_df["csv_timestamp_utc"].notna().all()
    )
    if use_utc:
        fit_df["fit_timestamp"] = fit_df["fit_timestamp_utc"]
        csv_df["csv_timestamp"] = csv_df["csv_timestamp_utc"]

    if "rr_intervals" not in fit_df:
        fit_df["rr_intervals"] = [[] for _ in range(len(fit_df))]

    fit_for_merge = fit_df[
        [
            "fit_timestamp",
            "heart_rate",
            "heart_rate_bpm",
            "hrv",
            "rr_interval",
            "rr_intervals",
            "device_type",
            "measurement_method",
            "signal_quality",
        ]
    ].copy()

    csv_for_merge = csv_df[
        [
            "csv_timestamp",
            "spo2",
            "pulse",
            "pulse_rate_bpm",
            "motion",
            "device_type",
            "measurement_method",
            "signal_quality",
        ]
    ].copy()

    fit_time_offset = 0
    alignment_method = "utc_nearest" if use_utc else "offset_nearest"
    if not use_utc:
        fit_time_offset = choose_fit_time_offset(
            fit_for_merge=fit_for_merge,
            csv_for_merge=csv_for_merge,
            tolerance_ms=tolerance_ms,
        )

    if fit_time_offset:
        fit_for_merge["fit_timestamp"] = (
            fit_for_merge["fit_timestamp"]
            + pd.Timedelta(hours=fit_time_offset)
        )

        fit_for_merge = fit_for_merge.sort_values(
            "fit_timestamp"
        )

    merged = pd.merge_asof(
        csv_for_merge,
        fit_for_merge,
        left_on="csv_timestamp",
        right_on="fit_timestamp",
        direction="nearest",
        tolerance=pd.Timedelta(
            milliseconds=tolerance_ms
        ),
    )

    result = []

    for _, row in merged.iterrows():
        csv_timestamp = row.get("csv_timestamp")
        fit_timestamp = row.get("fit_timestamp")

        synchronized = pd.notna(fit_timestamp)

        delta_ms = None

        if synchronized:
            delta_ms = int(
                abs(
                    (
                        csv_timestamp
                        - fit_timestamp
                    ).total_seconds()
                    * 1000
                )
            )

        result.append(
            {
                "timestamp": csv_timestamp.to_pydatetime(),

                "heart_rate": safe_value(
                    row.get("heart_rate")
                ),
                "heart_rate_bpm": safe_value(
                    row.get("heart_rate_bpm")
                ),
                "hrv": safe_value(
                    row.get("hrv")
                ),
                "rr_interval": safe_value(
                    row.get("rr_interval")
                ),
                "rr_intervals": safe_list(
                    row.get("rr_intervals")
                ),

                "spo2": safe_value(
                    row.get("spo2")
                ),
                "pulse": safe_value(
                    row.get("pulse")
                ),
                "pulse_rate_bpm": safe_value(
                    row.get("pulse_rate_bpm")
                ),
                "motion": safe_value(
                    row.get("motion")
                ),

                "hr_source_type": safe_value(
                    row.get("device_type_y")
                ) or "unknown",
                "hr_measurement_method": safe_value(
                    row.get("measurement_method_y")
                ) or "unknown",
                "hr_signal_quality": safe_value(
                    row.get("signal_quality_y")
                ) or "unknown",
                "pulse_source_type": safe_value(
                    row.get("device_type_x")
                ) or "unknown",
                "pulse_measurement_method": safe_value(
                    row.get("measurement_method_x")
                ) or "unknown",
                "pulse_signal_quality": safe_value(
                    row.get("signal_quality_x")
                ) or "unknown",
                "telemetry_schema_version": SCHEMA_VERSION,
                "timestamp_utc": (
                    csv_timestamp.to_pydatetime() if use_utc else None
                ),
                "fit_timestamp_utc": (
                    fit_timestamp.to_pydatetime()
                    if synchronized and use_utc
                    else None
                ),
                "csv_timestamp_utc": (
                    csv_timestamp.to_pydatetime() if use_utc else None
                ),
                "time_alignment_method": alignment_method,
                "time_alignment_quality": (
                    "high" if synchronized and use_utc
                    else "medium" if synchronized
                    else "low"
                ),

                "fit_timestamp": (
                    fit_timestamp.to_pydatetime()
                    if synchronized
                    else None
                ),
                "csv_timestamp": (
                    csv_timestamp.to_pydatetime()
                ),

                "delta_ms": delta_ms,
                "synchronized": synchronized,
                "fit_time_offset_hours": fit_time_offset,
            }
        )

    # FIT-level rolling RMSSD is retained when available; recompute only when
    # merging introduced a source classification unavailable at import time.
    if not any(row.get("hrv") is not None for row in result):
        annotate_hrv_rmssd_timeline(result)

    return result


def merge_csv_only(
    *,
    csv_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create a DURING timeline when only pulse oximeter CSV is available."""

    result = []

    for row in csv_rows:
        timestamp = row.get("timestamp")

        result.append({
            "timestamp": timestamp,
            "heart_rate": row.get("heart_rate_bpm"),
            "heart_rate_bpm": row.get("heart_rate_bpm"),
            "hrv": None,
            "rr_interval": None,
            "spo2": row.get("spo2"),
            "pulse": row.get("pulse"),
            "pulse_rate_bpm": row.get("pulse_rate_bpm") or row.get("pulse"),
            "motion": row.get("motion"),
            "hr_source_type": "unknown",
            "hr_measurement_method": "unknown",
            "hr_signal_quality": "unknown",
            "pulse_source_type": row.get("device_type") or "unknown",
            "pulse_measurement_method": (
                row.get("measurement_method") or "unknown"
            ),
            "pulse_signal_quality": row.get("signal_quality") or "unknown",
            "telemetry_schema_version": SCHEMA_VERSION,
            "timestamp_utc": row.get("timestamp_utc"),
            "fit_timestamp_utc": None,
            "csv_timestamp_utc": row.get("timestamp_utc"),
            "time_alignment_method": "single_source",
            "time_alignment_quality": "high",
            "fit_timestamp": None,
            "csv_timestamp": timestamp,
            "delta_ms": None,
            "synchronized": True,
            "fit_time_offset_hours": 0,
        })

    return result


def choose_fit_time_offset(
    *,
    fit_for_merge: pd.DataFrame,
    csv_for_merge: pd.DataFrame,
    tolerance_ms: int,
) -> int:
    """Choose the hour offset that gives the strongest FIT/CSV overlap.

    FIT timestamps from wearable exports are commonly UTC, while Checkme CSV exports are local
    wall-clock time without timezone information. Existing imports store both
    as naive timestamps, so merge-time offset selection keeps old data usable.
    """

    best_offset = 0
    best_score = (-1, float("-inf"))

    for offset_hours in TIME_OFFSET_CANDIDATE_HOURS:
        shifted_fit = fit_for_merge.copy()

        if offset_hours:
            shifted_fit["fit_timestamp"] = (
                shifted_fit["fit_timestamp"]
                + pd.Timedelta(hours=offset_hours)
            )

        shifted_fit = shifted_fit.sort_values(
            "fit_timestamp"
        )

        candidate = pd.merge_asof(
            csv_for_merge[["csv_timestamp"]],
            shifted_fit[["fit_timestamp"]],
            left_on="csv_timestamp",
            right_on="fit_timestamp",
            direction="nearest",
            tolerance=pd.Timedelta(
                milliseconds=tolerance_ms
            ),
        )

        matched = int(
            candidate["fit_timestamp"].notna().sum()
        )

        overlap_score = calculate_overlap_seconds(
            fit_start=shifted_fit["fit_timestamp"].min(),
            fit_end=shifted_fit["fit_timestamp"].max(),
            csv_start=csv_for_merge["csv_timestamp"].min(),
            csv_end=csv_for_merge["csv_timestamp"].max(),
        )

        score = (matched, overlap_score)

        if score > best_score:
            best_score = score
            best_offset = offset_hours

    return best_offset


def calculate_overlap_seconds(
    *,
    fit_start,
    fit_end,
    csv_start,
    csv_end,
) -> float:
    overlap_start = max(fit_start, csv_start)
    overlap_end = min(fit_end, csv_end)

    if overlap_end <= overlap_start:
        return 0.0

    return (
        overlap_end - overlap_start
    ).total_seconds()


def safe_value(value):
    """Convert pandas NaN/scalar values into JSON/database-friendly values."""

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        return value.item()

    return value


def safe_list(value):
    """Preserve list-like telemetry fields without applying scalar NaN rules."""

    if value is None:
        return []

    if isinstance(value, (list, tuple)):
        return list(value)

    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        return []

    return []


def first_not_none(*values):
    for value in values:
        if value is not None:
            return value

    return None
