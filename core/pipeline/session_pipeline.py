import pandas as pd
import numpy as np
from fitparse import FitFile
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


class SessionPipeline:

    def __init__(self, fit_path=None, csv_path=None):
        self.fit_path = fit_path
        self.csv_path = csv_path

        self.mode = None
        self.df_fit = None
        self.df_csv = None
        self.df = None

    # =========================
    # LOAD FIT
    # =========================
    def load_fit(self):
        if not self.fit_path:
            return None

        fitfile = FitFile(self.fit_path)
        records = []

        for record in fitfile.get_messages("record"):
            data = {f.name: f.value for f in record}

            records.append({
                "timestamp": data.get("timestamp"),
                "heart_rate": data.get("heart_rate"),
                "rr_interval": data.get("rr_interval"),
            })

        df = pd.DataFrame(records).dropna(subset=["timestamp"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        self.df_fit = df
        return df

    # =========================
    # LOAD CSV
    # =========================
    def load_csv(self):
        if not self.csv_path:
            return None

        df = pd.read_csv(self.csv_path)
        df["time"] = pd.to_datetime(df["time"])

        self.df_csv = df
        return df

    # =========================
    # MODE
    # =========================
    def detect_mode(self):
        if self.df_fit is not None and self.df_csv is not None:
            self.mode = "FULL"
        elif self.df_fit is not None:
            self.mode = "GARMIN_ONLY"
        elif self.df_csv is not None:
            self.mode = "OXI_ONLY"
        else:
            raise ValueError("No data")

    # =========================
    # MERGE + ALIGN (FIXED)
    # =========================
    def merge(self):

        if self.mode == "FULL":
            df = pd.merge_asof(
                self.df_fit.sort_values("timestamp"),
                self.df_csv.sort_values("time"),
                left_on="timestamp",
                right_on="time",
                direction="nearest",
                tolerance=pd.Timedelta("2s")
            )

        elif self.mode == "GARMIN_ONLY":
            df = self.df_fit.copy()
            df["spo2"] = np.nan
            df["pulse"] = np.nan

        else:
            df = self.df_csv.copy()
            df.rename(columns={"time": "timestamp"}, inplace=True)

        df = df.sort_values("timestamp")

        # 🔥 RESAMPLE 1s (IMPORTANT FIX)
        df = df.set_index("timestamp").resample("1s").mean().interpolate()

        self.df = df.reset_index()

    # =========================
    # FEATURES (FIXED HRV)
    # =========================
    def compute_features(self):
        df = self.df

        # HR smoothing
        df["hr_smooth"] = df["heart_rate"].ewm(span=10).mean()

        # HR trend
        df["hr_diff"] = df["hr_smooth"].diff()

        # RR HRV FIX (RMSSD rolling window corrected)
        if "rr_interval" in df:
            rr = df["rr_interval"]

            df["rmssd_30"] = rr.rolling(30).apply(
                lambda x: np.sqrt(np.mean(np.diff(x) ** 2)) if len(x) > 2 else np.nan
            )

            df["sdnn_30"] = rr.rolling(30).std()

        # cross features
        if "pulse" in df:
            df["hr_pulse_gap"] = df["heart_rate"] - df["pulse"]

        if "spo2" in df:
            df["spo2_std"] = df["spo2"].rolling(30).std()

        self.df = df

    # =========================
    # PHASE DETECTION (FIXED)
    # =========================
    def detect_phases(self):

        df = self.df

        df["dHR"] = df["hr_smooth"].diff().rolling(5).mean()

        df["phase"] = "plateau"

        df.loc[df["dHR"] > 0.3, "phase"] = "compression"
        df.loc[df["dHR"] < -0.3, "phase"] = "decompression"

        self.df = df

    # =========================
    # SESSION SEGMENTATION (FIXED)
    # =========================
    def segment_session(self):

        df = self.df

        start = df["timestamp"].min()
        end = df["timestamp"].max()

        df["session_phase"] = "IN"

        df.loc[df["timestamp"] < start + pd.Timedelta("5min"), "session_phase"] = "PRE"
        df.loc[df["timestamp"] > end - pd.Timedelta("5min"), "session_phase"] = "POST"

        df.loc[df["phase"] == "compression", "session_phase"] = "IN_COMPRESSION"
        df.loc[df["phase"] == "plateau", "session_phase"] = "IN_PLATEAU"
        df.loc[df["phase"] == "decompression", "session_phase"] = "IN_DECOMPRESSION"

        self.df = df

    # =========================
    # OAI (PLATEAU ONLY FIXED)
    # =========================
    def compute_oai(self):

        df = self.df.copy()

        df["oai"] = np.nan

        plateau = df[df["phase"] == "plateau"]

        if len(plateau) == 0:
            self.df = df
            return

        df.loc[df["phase"] == "plateau", "oai"] = (
            -plateau["hr_diff"] * 0.5 +
            plateau.get("rmssd_30", 0) * 0.5
        )

        self.df = df

    # =========================
    # ANOMALY (FIXED + NORMALIZED)
    # =========================
    def detect_anomalies(self):

        df = self.df.copy()

        features = [c for c in [
            "heart_rate",
            "rmssd_30",
            "spo2",
            "hr_pulse_gap"
        ] if c in df.columns]

        data = df[features].fillna(0)

        if len(data) < 50:
            df["anomaly"] = 0
            self.df = df
            return

        scaler = StandardScaler()
        X = scaler.fit_transform(data)

        model = IsolationForest(contamination=0.02, random_state=42)
        preds = model.fit_predict(X)

        df["anomaly"] = preds

        self.df = df

    # =========================
    # SUMMARY (FIXED)
    # =========================
    def summarize(self):

        df = self.df

        return {
            "hr_mean": df["heart_rate"].mean(),
            "rmssd_mean": df.get("rmssd_30", pd.Series()).mean(),
            "spo2_mean": df.get("spo2", pd.Series()).mean(),
            "oai_mean": df.get("oai", pd.Series()).mean(),
            "anomalies": int((df["anomaly"] == -1).sum())
        }

    # =========================
    # RUN PIPELINE
    # =========================
    def run(self):

        self.load_fit()
        self.load_csv()
        self.detect_mode()
        self.merge()
        self.compute_features()
        self.detect_phases()
        self.segment_session()
        self.compute_oai()
        self.detect_anomalies()

        return self.df, self.summarize()