import subprocess
import json
import os
import re
from datetime import datetime

RESULT_PATH = "data/performance/latest.json"
HISTORY_PATH = "data/performance/history.json"

os.makedirs("data/performance", exist_ok=True)

SIMULATIONS = {
    "sessions": "corelabtech.SessionsSimulation",
    "merge": "corelabtech.DuringMergeSimulation",
    "analysis": "corelabtech.RunAnalysisSimulation",
    "csv": "corelabtech.UploadCsvSimulation",
    "fit": "corelabtech.UploadFitSimulation",
}


def _extract_number(pattern, text, default=None):
    match = re.search(pattern, text)

    if not match:
        return default

    try:
        return float(match.group(1))
    except Exception:
        return default


def _extract_report_path(stdout):
    match = re.search(
        r"Reports generated.*file:///(.*?/index\.html)",
        stdout
    )

    if not match:
        return None

    return match.group(1).replace("\\", "/")


def _parse_gatling_stdout(stdout):
    return {
        "request_count": _extract_number(
            r"request count\s+(\d+)",
            stdout
        ),
        "min_ms": _extract_number(
            r"min response time\s+(\d+)",
            stdout
        ),
        "max_ms": _extract_number(
            r"max response time\s+(\d+)",
            stdout
        ),
        "mean_ms": _extract_number(
            r"mean response time\s+(\d+)",
            stdout
        ),
        "p50_ms": _extract_number(
            r"50th percentile\s+(\d+)",
            stdout
        ),
        "p75_ms": _extract_number(
            r"75th percentile\s+(\d+)",
            stdout
        ),
        "p95_ms": _extract_number(
            r"95th percentile\s+(\d+)",
            stdout
        ),
        "p99_ms": _extract_number(
            r"99th percentile\s+(\d+)",
            stdout
        ),
        "requests_per_sec": _extract_number(
            r"mean requests/sec\s+([0-9.]+)",
            stdout
        ),
        "failed_count": _extract_number(
            r"failed\s+(\d+)",
            stdout
        ),
        "success_rate": _extract_number(
            r"successful events is greater than.*actual : ([0-9.]+)",
            stdout,
            100.0
        ),
        "report_path": _extract_report_path(stdout),
    }


def _load_history():
    if not os.path.exists(HISTORY_PATH):
        return []

    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(entry):
    history = _load_history()

    history.append(entry)

    history = history[-50:]

    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def run_gatling_test(test_type):
    simulation = SIMULATIONS.get(test_type)

    if not simulation:
        return {
            "status": "error",
            "message": "Unknown simulation"
        }

    maven_cmd = "mvn.cmd" if os.name == "nt" else "mvn"

    cmd = [
        maven_cmd,
        "gatling:test",
        f"-Dgatling.simulationClass={simulation}"
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd="tests/performance/gatling",
            capture_output=True,
            text=True
        )

        metrics = _parse_gatling_stdout(result.stdout)

        passed = result.returncode == 0

        output = {
            "status": "success" if passed else "failed",
            "simulation": simulation,
            "test_type": test_type,
            "returncode": result.returncode,
            "metrics": metrics,
            "summary": {
                "result": "PASS" if passed else "FAIL",
                "gate": "P95 < threshold and success rate > 95%",
                "report": metrics.get("report_path") or "target/gatling"
            },
            "stdout": result.stdout[-6000:],
            "stderr": "" if passed else result.stderr[-3000:],
            "generated_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        output = {
            "status": "error",
            "simulation": simulation,
            "test_type": test_type,
            "message": str(e),
            "generated_at": datetime.utcnow().isoformat()
        }

    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    _save_history(output)

    return output


def get_performance_history():
    return _load_history()


def get_latest_performance_result():
    if not os.path.exists(RESULT_PATH):
        return {
            "status": "no_results"
        }

    with open(RESULT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)