import subprocess
import os
import json
from datetime import datetime

RESULT_LOG = "data/playwright_runs.json"

os.makedirs("data", exist_ok=True)
os.makedirs("playwright-report", exist_ok=True)


def run_playwright_tests():
    cmd = [
        "npx.cmd" if os.name == "nt" else "npx",
        "playwright",
        "test"
    ]

    try:
        env = {
            **os.environ,
            "ENV_FILE": os.getenv("ENV_FILE", ".env.local"),
        }

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=os.getcwd(),
            timeout=120,
            env=env,
        )

        output = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "success" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": " ".join(cmd),
            "report_path": "playwright-report/index.html"
        }
    except subprocess.TimeoutExpired as e:
        output = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "error",
            "returncode": None,
            "error": "Playwright execution timeout",
            "stdout": (e.stdout or "")[-12000:] if e.stdout else "",
            "stderr": (e.stderr or "")[-5000:] if e.stderr else "",
            "command": " ".join(cmd),
            "report_path": "playwright-report/index.html"
        }
    except Exception as e:
        output = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "error",
            "returncode": None,
            "error": str(e),
            "command": " ".join(cmd)
        }

    with open(RESULT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(output, ensure_ascii=False) + "\n")

    return output