"""`POST /api/v1/exports` en modo local (`{"path": ...}`), spec 06 CA-9."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_export_md_api.main import app

PROBLEM_JSON = "application/problem+json"


def test_local_mode_is_off_by_default(synthetic_export_dir: Path) -> None:
    client = TestClient(app)
    response = client.post("/api/v1/exports", json={"path": str(synthetic_export_dir)})

    assert response.status_code == 403
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["status"] == 403
    assert "CEM_ALLOW_LOCAL_PATHS" in body["detail"]


def test_local_mode_stays_off_when_the_flag_is_not_literally_true(
    monkeypatch: pytest.MonkeyPatch, synthetic_export_dir: Path
) -> None:
    monkeypatch.setenv("CEM_ALLOW_LOCAL_PATHS", "1")
    client = TestClient(app)
    response = client.post("/api/v1/exports", json={"path": str(synthetic_export_dir)})

    assert response.status_code == 403


def test_local_mode_accepts_a_valid_path_when_enabled(
    monkeypatch: pytest.MonkeyPatch, synthetic_export_dir: Path
) -> None:
    monkeypatch.setenv("CEM_ALLOW_LOCAL_PATHS", "true")
    client = TestClient(app)
    response = client.post("/api/v1/exports", json={"path": str(synthetic_export_dir)})

    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["export_id"], str) and body["export_id"]


def test_local_mode_rejects_a_path_that_does_not_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CEM_ALLOW_LOCAL_PATHS", "true")
    client = TestClient(app)
    missing = tmp_path / "no-existe"

    response = client.post("/api/v1/exports", json={"path": str(missing)})

    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM_JSON


def test_local_mode_rejects_a_body_without_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CEM_ALLOW_LOCAL_PATHS", "true")
    client = TestClient(app)

    response = client.post("/api/v1/exports", json={"not_path": "whatever"})

    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM_JSON


def test_export_url_field_is_ignored_even_if_present(
    monkeypatch: pytest.MonkeyPatch, synthetic_export_dir: Path
) -> None:
    """CLAUDE.md 5: el export_url del manifiesto nunca se usa, ni siquiera si se manda."""
    monkeypatch.setenv("CEM_ALLOW_LOCAL_PATHS", "true")
    client = TestClient(app)

    response = client.post(
        "/api/v1/exports",
        json={"path": str(synthetic_export_dir), "export_url": "https://example.invalid/x"},
    )

    assert response.status_code == 201
