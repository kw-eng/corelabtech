"""Quarantined legacy credential maintenance script.

This utility is intentionally non-operational. Account rotation must use the
approved operator process and environment-backed credential boundary.
"""


def main() -> None:
    raise RuntimeError(
        "This legacy credential-maintenance script is quarantined and cannot run."
    )


if __name__ == "__main__":
    main()
