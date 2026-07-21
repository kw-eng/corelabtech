# Pipeline Runner
from services.analysis_service import run_session_analysis
from services.data_merge import merge_session_data

from core.qa.playwright_runner import run_playwright_tests


def run_full_pipeline(session_id):

    # =========================
    # MERGE
    # =========================
    merge_result = merge_session_data(
        session_id=session_id
    )

    # =========================
    # AI ANALYSIS
    # =========================
    analysis_result = run_session_analysis(
        session_id=session_id
    )

    # =========================
    # AUTO QA RUN
    # =========================
    qa_result = run_playwright_tests()

    return {
        "status": "completed",
        "session_id": session_id,
        "merge": merge_result.to_dict(),
        "analysis": analysis_result.to_dict(),
        "qa": qa_result
    }
