def detect_flaky(playwright_result):

    stderr = playwright_result.get("stderr", "").lower()

    flaky_patterns = [
        "timeout",
        "locator",
        "element is not attached",
        "networkidle",
        "detached"
    ]

    found = []

    for p in flaky_patterns:
        if p in stderr:
            found.append(p)

    return {
        "flaky": len(found) > 0,
        "patterns": found
    }