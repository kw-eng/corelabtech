# services/fit_parser.py

from collections import deque
import math

RR_MIN_SECONDS = 0.3
RR_MAX_SECONDS = 2.0
RR_MAX_DELTA_SECONDS = 0.15
RR_MAX_DELTA_RATIO = 0.20


# =========================================================
# SAFE FLOAT
# =========================================================

def safe_float(v):

    try:
        return float(v)
    except:
        return None


# =========================================================
# HRV
# =========================================================

def calculate_hrv(rr_intervals):
    return calculate_rmssd(rr_intervals)


def calculate_rmssd(values):
    rr = [
        value
        for value in values
        if value is not None
    ]

    if len(rr) < 2:
        return None

    squared_diffs = [
        (current - previous) ** 2
        for previous, current in zip(rr, rr[1:])
    ]

    return round(
        calculate_rmssd_raw(rr),
        2,
    )


def calculate_rmssd_raw(values):
    if len(values) < 2:
        return None

    squared_diffs = [
        (current - previous) ** 2
        for previous, current in zip(values, values[1:])
    ]

    return math.sqrt(
        sum(squared_diffs) / len(squared_diffs)
    )


def calculate_rmssd_ms(values):
    clean = [
        value
        for value in values
        if value is not None
    ]

    result = calculate_rmssd_raw(clean)

    if result is None:
        return None

    if max(clean) < 10:
        result *= 1000

    return round(result, 2)


def is_valid_rr_interval(value):
    return (
        value is not None
        and RR_MIN_SECONDS <= value <= RR_MAX_SECONDS
    )


def is_rr_artifact(value, previous_value):
    if not is_valid_rr_interval(value):
        return True

    if previous_value is None:
        return False

    delta = abs(value - previous_value)
    ratio = (
        delta / previous_value
        if previous_value
        else 0
    )

    return (
        delta > RR_MAX_DELTA_SECONDS
        or ratio > RR_MAX_DELTA_RATIO
    )


def append_filtered_rr(rr_window, value, previous_value):
    if is_rr_artifact(value, previous_value):
        return previous_value, True

    rr_window.append(value)

    return value, False


def normalize_timestamp(value):
    if value is None:
        return None

    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def extract_rr_values(value):
    if isinstance(value, (list, tuple)):
        return [
            safe_float(item)
            for item in value
            if safe_float(item) is not None
        ]

    normalized = safe_float(value)

    return (
        [normalized]
        if normalized is not None
        else []
    )


def extract_hrv_packets(fitfile):
    packets = []

    try:
        for message in fitfile.get_messages("hrv"):
            rr_values = []

            for field in message:
                name = str(field.name).lower()

                if name in [
                    "time",
                    "rr_interval",
                    "rr",
                    "rr_intervals",
                ]:
                    rr_values.extend(
                        extract_rr_values(field.value)
                    )

            if rr_values:
                packets.append(rr_values)

    except Exception as exc:
        print("FIT HRV PARSE ERROR:", exc)

    return packets


def apply_hrv_packets(rows, hrv_packets):
    if not rows or not hrv_packets:
        return

    rr_window = deque(maxlen=31)
    previous_rr = None

    for index, row in enumerate(rows):
        packet = (
            hrv_packets[index]
            if index < len(hrv_packets)
            else []
        )

        if packet and row.get("rr_interval") is None:
            row["rr_interval"] = packet[0]

        row_artifact = False

        for value in packet:
            previous_rr, artifact = append_filtered_rr(
                rr_window,
                value,
                previous_rr,
            )
            row_artifact = row_artifact or artifact

        row["hrv"] = calculate_rmssd_ms(rr_window)
        row["rr_artifact"] = row_artifact


# =========================================================
# FIT PARSER
# =========================================================

def parse_fit_file(file_path):
    try:
        from fitparse import FitFile
    except ImportError as e:
        raise RuntimeError(
            "FIT parser dependency is missing: install fitparse"
        ) from e

    rows = []

    try:

        fitfile = FitFile(str(file_path))

    except Exception as e:

        print("FIT OPEN ERROR:", e)

        raise

    try:

        hrv_packets = extract_hrv_packets(fitfile)

        for record in fitfile.get_messages("record"):

            row = {

                "timestamp": None,

                "heart_rate": None,

                "pulse": None,

                "spo2": None,

                "rr_interval": None,

                "hrv": None,

                "source": "fit"
            }

            try:

                for field in record:

                    name = str(field.name).lower()

                    value = field.value

                    # =============================
                    # TIME
                    # =============================

                    if name == "timestamp":

                        row["timestamp"] = normalize_timestamp(value)

                    # =============================
                    # HEART RATE
                    # =============================

                    elif name in [
                        "heart_rate",
                        "hr",
                        "pulse"
                    ]:

                        row["heart_rate"] = value
                        row["pulse"] = value

                    # =============================
                    # SPO2
                    # =============================

                    elif name in [
                        "spo2",
                        "oxygen_saturation"
                    ]:

                        row["spo2"] = value

                    # =============================
                    # RR
                    # =============================

                    elif name in [
                        "rr_interval",
                        "rr",
                        "rr_intervals"
                    ]:

                        if isinstance(value, list):

                            if len(value):

                                row["rr_interval"] = safe_float(
                                    value[0]
                                )

                        else:

                            row["rr_interval"] = safe_float(
                                value
                            )

                # =====================================
                # SAVE PARTIAL ROWS
                # =====================================

                if (
                    row["timestamp"] is not None
                    or row["heart_rate"] is not None
                ):

                    rows.append(row)

            except Exception as e:

                print("FIT RECORD ERROR:", e)

                continue

    except Exception as e:

        print("FIT PARSE ERROR:", e)

        return []

    # =========================================
    # EMPTY
    # =========================================

    if not rows:
        return []

    # =========================================
    # HRV
    # =========================================

    try:

        apply_hrv_packets(rows, hrv_packets)

        rr_window = deque(maxlen=31)
        previous_rr = None

        for row in rows:

            if row.get("hrv") is not None:
                continue

            previous_rr, artifact = append_filtered_rr(
                rr_window,
                row.get("rr_interval"),
                previous_rr,
            )
            row["rr_artifact"] = artifact

            row["hrv"] = calculate_rmssd_ms(rr_window)

    except Exception as e:

        print("HRV ERROR:", e)

    # =========================================
    # CLEANUP
    # =========================================

    for row in rows:
        for key, value in list(row.items()):
            if isinstance(value, float) and math.isnan(value):
                row[key] = None

    return rows
