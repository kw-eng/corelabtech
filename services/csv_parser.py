# services/csv_parser.py

import pandas as pd
import numpy as np


# =========================================================
# SAFE FLOAT
# =========================================================

def safe_float(v):

    try:

        if pd.isna(v):
            return None

        return float(v)

    except:

        return None


# =========================================================
# NORMALIZE COLUMN
# =========================================================

def normalize_column(name):

    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "_")
    )


# =========================================================
# CSV PARSER
# =========================================================

def parse_csv_file(path):

    try:

        df = pd.read_csv(path)

    except Exception as e:

        print("CSV READ ERROR:", e)

        return []

    print("CSV COLUMNS:", df.columns.tolist())

    # =====================================================
    # NORMALIZE COLUMNS
    # =====================================================

    df.columns = [
        normalize_column(c)
        for c in df.columns
    ]

    print("NORMALIZED:", df.columns.tolist())

    rows = []

    # =====================================================
    # ITERATE ROWS
    # =====================================================

    for _, r in df.iterrows():

        row = {

            "timestamp": None,

            "pulse": None,

            "heart_rate": None,

            "spo2": None,

            "source": "csv"
        }

        # =================================================
        # TIME
        # =================================================

        for col in [

            "timestamp",
            "time",
            "datetime",
            "date",
            "date_time"

        ]:

            if col in df.columns:

                try:

                    row["timestamp"] = str(
                        pd.to_datetime(r[col])
                    )

                except:

                    row["timestamp"] = str(r[col])

                break

        # =================================================
        # PULSE / HR
        # =================================================

        for col in [

            "pulse",
            "heart_rate",
            "hr",
            "bpm"

        ]:

            if col in df.columns:

                val = safe_float(r[col])

                row["pulse"] = val
                row["heart_rate"] = val

                break

        # =================================================
        # SPO2
        # =================================================

        for col in [

            "spo2",
            "sp02",
            "s02",
            "so2",

            "spo₂",

            "oxygen",
            "saturation",
            "oxygen_saturation",

            "blood_oxygen",

            "o2",
            "sat"

        ]:

            if col in df.columns:

                row["spo2"] = safe_float(
                    r[col]
                )

                break

        # =================================================
        # DEBUG
        # =================================================

        print("CSV ROW:", row)
        print("CSV SPO2:", row["spo2"])

        rows.append(row)

    # =====================================================
    # CLEAN EMPTY
    # =====================================================

    clean = []

    for r in rows:

        if (

            r["timestamp"] is not None

            or r["pulse"] is not None

            or r["spo2"] is not None

        ):

            clean.append(r)

    print("FINAL CSV:", len(clean))

    return clean