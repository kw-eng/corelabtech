"""Production startup checks for Flask signing-key configuration."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORT_APP = "import app; print('app-imported')"


def import_app_with_environment(
    *, app_env: str, secret_key: str | None, working_directory: Path
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["APP_ENV"] = app_env
    environment["FLASK_ENV"] = app_env
    environment["PYTHONPATH"] = str(ROOT)
    if secret_key is None:
        environment.pop("SECRET_KEY", None)
    else:
        environment["SECRET_KEY"] = secret_key
    return subprocess.run(
        [sys.executable, "-c", IMPORT_APP],
        cwd=working_directory,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("secret_key", [None, "", "CHANGE_ME", "change-me", "short-secret"])
def test_production_rejects_missing_placeholder_and_short_secret_keys(
    secret_key: str | None, tmp_path: Path
):
    result = import_app_with_environment(
        app_env="production", secret_key=secret_key, working_directory=tmp_path
    )

    assert result.returncode != 0
    assert "SECRET_KEY must be set to a strong, non-default value in production." in result.stderr


def test_production_accepts_strong_secret_key(tmp_path: Path):
    result = import_app_with_environment(
        app_env="production", secret_key="s" * 32, working_directory=tmp_path
    )

    assert result.returncode == 0, result.stderr
    assert "app-imported" in result.stdout


def test_development_keeps_legacy_secret_key_compatibility(tmp_path: Path):
    result = import_app_with_environment(
        app_env="development", secret_key="CHANGE_ME", working_directory=tmp_path
    )

    assert result.returncode == 0, result.stderr
    assert "app-imported" in result.stdout
