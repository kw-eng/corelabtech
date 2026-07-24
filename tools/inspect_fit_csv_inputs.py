from __future__ import annotations

import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from fitparse import FitFile


FIT_PATH = Path(r"D:\corelabtech_final_clean\files\fenix8\23664778759_ACTIVITY.fit")
CSV_PATH = Path(r"D:\corelabtech_final_clean\files\checkme\Checkme O2 _20260720130928.csv")


def numeric_stats(values: list[float]) -> str:
    if not values:
        return "count=0"
    return (
        f"count={len(values)} "
        f"min={min(values)} "
        f"avg={round(statistics.mean(values), 2)} "
        f"max={max(values)}"
    )


def inspect_csv() -> None:
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
    print("CSV")
    print("file:", CSV_PATH.name)
    print("bytes:", CSV_PATH.stat().st_size)
    print("rows:", len(rows))
    print("columns:", list(rows[0].keys()) if rows else [])
    print("first:", rows[0] if rows else None)
    print("last:", rows[-1] if rows else None)

    for column in ["Oxygen Level", "Pulse Rate", "Motion", "O2 Reminder", "PR Reminder"]:
        values = [
            float(row[column])
            for row in rows
            if row.get(column) not in (None, "")
        ]
        print(column + ":", numeric_stats(values))


def inspect_fit() -> None:
    fit = FitFile(str(FIT_PATH))
    msg_counts: Counter[str] = Counter()
    fields_by_msg: defaultdict[str, Counter[str]] = defaultdict(Counter)
    records: list[dict] = []
    hrv_packets: list[list[float]] = []

    for msg in fit.get_messages():
        msg_counts[msg.name] += 1
        for field in msg:
            fields_by_msg[msg.name][str(field.name).lower()] += 1

        if msg.name == "record":
            records.append({
                str(field.name).lower(): field.value
                for field in msg
            })
        elif msg.name == "hrv":
            packet = []
            for field in msg:
                name = str(field.name).lower()
                value = field.value
                if name not in {"time", "rr_interval", "rr", "rr_intervals"}:
                    continue
                if isinstance(value, (list, tuple)):
                    packet.extend(
                        float(item)
                        for item in value
                        if item is not None
                    )
                elif value is not None:
                    packet.append(float(value))
            if packet:
                hrv_packets.append(packet)

    print("\nFIT")
    print("file:", FIT_PATH.name)
    print("bytes:", FIT_PATH.stat().st_size)
    print("message_counts:", msg_counts.most_common(30))
    print("record_count:", len(records))
    print("record_fields:", sorted(fields_by_msg["record"].keys()))
    print("hrv_message_count:", msg_counts.get("hrv", 0))
    print("hrv_packets_with_values:", len(hrv_packets))
    print("rr_values_in_hrv_messages:", sum(len(packet) for packet in hrv_packets))
    print("hrv_fields:", sorted(fields_by_msg["hrv"].keys()))

    def nums(field: str) -> list[float]:
        values = []
        for record in records:
            value = record.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))
        return values

    for field in [
        "heart_rate",
        "rr_interval",
        "hrv",
        "saturated_hemoglobin_percent",
        "respiration_rate",
        "enhanced_speed",
        "speed",
        "distance",
        "altitude",
        "enhanced_altitude",
        "temperature",
        "cadence",
    ]:
        print(field + ":", numeric_stats(nums(field)))

    timestamps = [
        record.get("timestamp")
        for record in records
        if record.get("timestamp") is not None
    ]
    print("timestamp_count:", len(timestamps))
    print("first_timestamp:", min(timestamps) if timestamps else None)
    print("last_timestamp:", max(timestamps) if timestamps else None)

    print("record_rr_or_hrv_fields:", [
        field
        for field in sorted(fields_by_msg["record"].keys())
        if "rr" in field or "hrv" in field
    ])

    print("\nRelevant FIT messages")
    for message_name in sorted(msg_counts):
        keys = sorted(fields_by_msg[message_name].keys())
        if (
            message_name in {"activity", "device_info", "event", "file_id", "lap", "session", "sport"}
            or any(
                token in key
                for key in keys
                for token in ["heart", "hrv", "rr", "spo2", "oxygen", "hemoglobin", "respiration"]
            )
        ):
            print(message_name, "count=", msg_counts[message_name], "fields=", keys)


if __name__ == "__main__":
    inspect_csv()
    inspect_fit()
