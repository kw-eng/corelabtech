# AI ENGINE
#    ↓
# run_ai_analysis()
#    ↓
# ├── ai_logs.json  ← dataset (ML / flaky)
# ├── explanation
# └── output

#    ↓

# TEST GENERATOR
#    ↓
# ├── Playwright test
# ├── TAGS (anomaly/hrv/spo2)
# └── assertions
import json
import os
from datetime import datetime

OUTPUT_DIR = "tests/generated"
LOG_FILE = "data/ai_logs.json"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)


# =========================
# MAIN GENERATOR
# =========================
def generate_playwright_test(input_data, ai_output):

    test_name = _build_test_name(ai_output)
    tags = _build_tags(ai_output)

    filename = f"{OUTPUT_DIR}/test_{int(datetime.now().timestamp())}.spec.ts"

    test_code = f"""
import {{ test, expect }} from '@playwright/test';

test('{test_name}', async () => {{

  const input = {json.dumps(input_data, indent=2)};
  const result = {json.dumps(ai_output, indent=2)};

  // 🔥 TAGS: {tags}

  expect(result.anomaly).toBe({str(ai_output.get("anomaly", False)).lower()});

  {"".join(_build_expects(ai_output))}

}});
"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(test_code)

    # =========================
    # 🔥 AI LOGGING (WAŻNE)
    # =========================
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "input": input_data,
            "output": ai_output,
            "tags": tags
        }) + "\n")

    return {
        "file": filename,
        "test_name": test_name,
        "tags": tags
    }


# =========================
# HELPERS
# =========================

def _build_test_name(ai_output):
    if ai_output.get("anomaly"):
        return "AI detects anomaly correctly"
    return "AI returns normal state"


def _build_expects(ai_output):
    lines = []

    for e in ai_output.get("explanation", []):
        lines.append(f"expect(result.explanation).toContain('{e}');\n")

    return lines


def _build_tags(ai_output):
    tags = []

    if ai_output.get("anomaly"):
        tags.append("anomaly")

    explanation = ai_output.get("explanation", [])

    if any("HRV" in e for e in explanation):
        tags.append("hrv")

    if any("oxygen" in e.lower() for e in explanation):
        tags.append("spo2")

    if any("heart" in e.lower() for e in explanation):
        tags.append("cardio")

    return tags