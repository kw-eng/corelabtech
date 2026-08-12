"""Fail-closed checks for legacy E2E credential handling.

These tests intentionally inspect only configuration structure and generated
test values.  They never read, compare, or print stored credentials.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
import uuid
from pathlib import Path

import pytest


SEED_PATH = Path(__file__).resolve().parents[1] / "seed_postgres_db.py"
MANUAL_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "change_passwords.py"


def _load_seed_module(monkeypatch: pytest.MonkeyPatch):
    """Load the credential helper without opening a database connection."""

    monkeypatch.setitem(sys.modules, "database_postgres", types.SimpleNamespace(db=None))
    spec = importlib.util.spec_from_file_location("legacy_seed_credential_boundary", SEED_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("missing_variable", ["E2E_ADMIN_PASSWORD", "E2E_RESEARCHER_PASSWORD"])
def test_missing_credential_fails_closed(monkeypatch: pytest.MonkeyPatch, missing_variable: str):
    module = _load_seed_module(monkeypatch)
    monkeypatch.setenv("E2E_ADMIN_PASSWORD", uuid.uuid4().hex)
    monkeypatch.setenv("E2E_RESEARCHER_PASSWORD", uuid.uuid4().hex)
    monkeypatch.delenv(missing_variable)

    with pytest.raises(RuntimeError, match="Required E2E credential environment variable is missing or empty"):
        module.seed_postgres_db()


@pytest.mark.parametrize("empty_variable", ["E2E_ADMIN_PASSWORD", "E2E_RESEARCHER_PASSWORD"])
def test_empty_credential_fails_closed(monkeypatch: pytest.MonkeyPatch, empty_variable: str):
    module = _load_seed_module(monkeypatch)
    monkeypatch.setenv("E2E_ADMIN_PASSWORD", uuid.uuid4().hex)
    monkeypatch.setenv("E2E_RESEARCHER_PASSWORD", uuid.uuid4().hex)
    monkeypatch.setenv(empty_variable, "")

    with pytest.raises(RuntimeError, match="Required E2E credential environment variable is missing or empty"):
        module.seed_postgres_db()


@pytest.mark.parametrize(
    "placeholder",
    ["CHANGE_ME", " change-me ", "change_me", "dev-secret-change-me", "corelabtech"],
)
def test_placeholder_credential_fails_closed(monkeypatch: pytest.MonkeyPatch, placeholder: str):
    module = _load_seed_module(monkeypatch)
    monkeypatch.setenv("E2E_ADMIN_PASSWORD", placeholder)
    monkeypatch.setenv("E2E_RESEARCHER_PASSWORD", uuid.uuid4().hex)

    with pytest.raises(RuntimeError, match="uses a placeholder value"):
        module.seed_postgres_db()


def test_seed_source_uses_no_getenv_fallback_and_preserves_hash_boundary():
    tree = ast.parse(SEED_PATH.read_text(encoding="utf-8"))
    credential_getenv_calls = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name)
            and target.id in {"admin_password", "researcher_password"}
            for target in node.targets
        ):
            assert isinstance(node.value, ast.Call)
            assert isinstance(node.value.func, ast.Attribute)
            assert node.value.func.attr == "getenv"
            assert len(node.value.args) == 1
            assert not node.value.keywords
            credential_getenv_calls.append(node.value)

    assert len(credential_getenv_calls) == 2
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "generate_password_hash"
        for node in ast.walk(tree)
    )


def test_legacy_manual_credential_maintenance_is_quarantined():
    source = MANUAL_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "quarantined" in source.lower()
    assert "generate_password_hash" not in source
    assert "os.getenv" not in source
