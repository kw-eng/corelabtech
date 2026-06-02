# Pipeline Runner
import json

from services.data_ingestion import load_fit
from services.data_ingestion import load_csv

from services.data_merge import merge_during

from services.ai_engine import run_ai_analysis

from services.test_generator import generate_playwright_test

from core.qa.playwright_runner import run_playwright_tests


AI_LOG = "data/ai_logs.json"


def run_full_pipeline(session_id):

    # =========================
    # LOAD
    # =========================
    fit_rows = load_fit(session_id)

    csv_rows = load_csv(session_id)

    # =========================
    # MERGE
    # =========================
    merged = merge_during(
        fit_rows,
        csv_rows
    )

    results = []

    # =========================
    # AI LOOP
    # =========================
    for row in merged:

        ai_output = run_ai_analysis(
            spo2=row.get("spo2"),
            pulse=row.get("pulse"),
            hrv=row.get("hrv"),
            ata=row.get("ata"),
            temp=row.get("temp")
        )

        # =========================
        # DATASET LOGGING
        # =========================
        with open(AI_LOG, "a", encoding="utf-8") as f:

            f.write(json.dumps({
                "input": row,
                "output": ai_output
            }) + "\n")

        # =========================
        # GENERATE TEST
        # =========================
        generate_playwright_test(
            row,
            ai_output
        )

        results.append(ai_output)

    # =========================
    # AUTO QA RUN
    # =========================
    qa_result = run_playwright_tests()

    return {
        "rows": len(merged),
        "ai_results": results,
        "qa": qa_result
    }