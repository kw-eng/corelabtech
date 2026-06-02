# tools/generate_csv_from_fit.py

from fitparse import FitFile
import pandas as pd
import random
import os
import sys


def generate_csv_from_fit(fit_path, output_csv):
    """
    Generates CSV with the same timestamps as FIT file.

    Output columns:
    timestamp,pulse,spo2
    """

    if not os.path.exists(fit_path):
        raise FileNotFoundError(f"FIT file not found: {fit_path}")

    output_dir = os.path.dirname(output_csv)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    fit = FitFile(fit_path)

    rows = []

    for record in fit.get_messages("record"):

        timestamp = None
        heart_rate = None

        for field in record:

            if field.name == "timestamp":
                timestamp = field.value

            elif field.name == "heart_rate":
                heart_rate = field.value

        if timestamp is not None:

            rows.append({
                "timestamp": pd.to_datetime(timestamp).isoformat(),
                "pulse": heart_rate if heart_rate is not None else "",
                "spo2": random.choice([97, 98, 98, 99])
            })

    df = pd.DataFrame(rows)

    df.to_csv(output_csv, index=False)

    print("[OK] CSV generated")
    print("[OK] FIT:", fit_path)
    print("[OK] CSV:", output_csv)
    print("[OK] Rows:", len(df))


if __name__ == "__main__":

    if len(sys.argv) != 3:

        print("Usage:")
        print("python tools/generate_csv_from_fit.py <input.fit> <output.csv>")
        sys.exit(1)

    generate_csv_from_fit(
        sys.argv[1],
        sys.argv[2]
    )