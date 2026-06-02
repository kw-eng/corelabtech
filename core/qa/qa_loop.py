# QA Loop
# core/qa/qa_loop.py

from core.qa.playwright_runner import (
    run_playwright_tests
)


def run_qa_loop():

    result = run_playwright_tests()

    return {
        "status": "completed",
        "playwright": result
    }