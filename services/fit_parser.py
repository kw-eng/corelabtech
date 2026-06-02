# services/fit_parser.py

from fitparse import FitFile
import pandas as pd
import numpy as np


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

    rr = np.array([
        r for r in rr_intervals
        if r is not None
    ])

    if len(rr) < 2:
        return None

    diff = np.diff(rr)

    rmssd = np.sqrt(np.mean(diff ** 2))

    return round(float(rmssd), 2)


# =========================================================
# FIT PARSER
# =========================================================

def parse_fit_file(file_path):

    rows = []

    try:

        fitfile = FitFile(file_path)

    except Exception as e:

        print("FIT OPEN ERROR:", e)

        return []

    try:

        for record in fitfile.get_messages():

            # =========================================
            # ONLY RECORDS
            # =========================================

            if record.name != "record":
                continue

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

                        row["timestamp"] = str(value)

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
    # DATAFRAME
    # =========================================

    try:

        df = pd.DataFrame(rows)

    except Exception as e:

        print("FIT DF ERROR:", e)

        return rows

    # =========================================
    # HRV
    # =========================================

    try:

        rr_values = df["rr_interval"].tolist()

        hrv_values = []

        for i in range(len(rr_values)):

            window = rr_values[
                max(0, i - 30):i + 1
            ]

            hrv_values.append(
                calculate_hrv(window)
            )

        df["hrv"] = hrv_values

    except Exception as e:

        print("HRV ERROR:", e)

    # =========================================
    # CLEANUP
    # =========================================

    df = df.replace({
        np.nan: None
    })

    return df.to_dict(
        orient="records"
    )