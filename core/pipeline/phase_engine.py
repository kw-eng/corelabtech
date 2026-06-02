# Phase Engine
# core/pipeline/phase_engine.py

import pandas as pd
import numpy as np


# =========================================================
# PHASE DETECTION
# =========================================================

def detect_session_phases(df):
    """
    Detect HBOT phases using HR trend

    Returns:
    compression
    plateau
    decompression
    """

    if df.empty:
        return df

    if "heart_rate" not in df.columns:
        df["phase"] = "unknown"
        return df

    # =====================================================
    # SMOOTH HR
    # =====================================================

    df["hr_smooth"] = (
        df["heart_rate"]
        .rolling(30, min_periods=1)
        .mean()
    )

    # =====================================================
    # DERIVATIVE
    # =====================================================

    df["dhr"] = df["hr_smooth"].diff()

    # =====================================================
    # PHASE RULES
    # =====================================================

    conditions = [

        # compression
        df["dhr"] > 0.2,

        # decompression
        df["dhr"] < -0.2,

        # plateau
        df["dhr"].abs() <= 0.2
    ]

    choices = [
        "compression",
        "decompression",
        "plateau"
    ]

    df["phase"] = np.select(
        conditions,
        choices,
        default="plateau"
    )

    return df


# =========================================================
# SESSION SEGMENTATION
# =========================================================

def segment_session_phases(df):
    """
    PRE / IN / POST segmentation
    """

    if df.empty:
        return df

    timestamp_col = None

    # =====================================================
    # TIMESTAMP DETECTION
    # =====================================================

    if "timestamp" in df.columns:
        timestamp_col = "timestamp"

    elif "time" in df.columns:
        timestamp_col = "time"

    if timestamp_col is None:
        df["session_phase"] = "UNKNOWN"
        return df

    # =====================================================
    # DATETIME
    # =====================================================

    df[timestamp_col] = pd.to_datetime(
        df[timestamp_col]
    )

    start = df[timestamp_col].min()
    end = df[timestamp_col].max()

    df["session_phase"] = "IN"

    # =====================================================
    # PRE
    # =====================================================

    df.loc[
        df[timestamp_col] < start + pd.Timedelta("5min"),
        "session_phase"
    ] = "PRE"

    # =====================================================
    # POST
    # =====================================================

    df.loc[
        df[timestamp_col] > end - pd.Timedelta("5min"),
        "session_phase"
    ] = "POST"

    # =====================================================
    # DURING PHASES
    # =====================================================

    if "phase" in df.columns:

        df.loc[
            df["phase"] == "compression",
            "session_phase"
        ] = "IN_COMPRESSION"

        df.loc[
            df["phase"] == "plateau",
            "session_phase"
        ] = "IN_PLATEAU"

        df.loc[
            df["phase"] == "decompression",
            "session_phase"
        ] = "IN_DECOMPRESSION"

    return df