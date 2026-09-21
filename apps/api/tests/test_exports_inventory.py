"""`GET /api/v1/exports/{id}/inventory`, spec 06."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_export_md_api.main import app

PROBLEM_JSON = "application/problem+json"


def test_inventory_of_a_registered_local_export(
    monkeypatch: pytest.MonkeyPatch, synthetic_export_dir: Path
) -> None:
    monkeypatch.setenv("CEM_ALLOW_LOCAL_PATHS", "true")
    client = TestClient(app)
    created = client.post("/api/v1/exports", json={"path": str(synthetic_export_dir)})
    export_id = created.json()["export_id"]

    response = client.get(f"/api/v1/exports/{export_id}/inventory")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["format_version"] == "batched-manifest"
    assert {"conversations", "memories", "projects", "frames", "light_metadata"} <= set(
        body["categories"]
    )
    # Sin fecha de la corrida ni ruta absoluta del disco del usuario (CLAUDE.md 5/1.4).
    assert body["root"] == synthetic_export_dir.name


def test_inventory_of_an_unknown_export_id_is_404() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/exports/does-not-exist/inventory")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON


def test_inventory_translates_a_core_error_into_422(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CEM_ALLOW_LOCAL_PATHS", "true")
    weird = tmp_path / "not-an-export.txt"
    weird.write_text("hola", encoding="utf-8")
    client = TestClient(app)
    created = client.post("/api/v1/exports", json={"path": str(weird)})
    assert created.status_code == 201
    export_id = created.json()["export_id"]

    response = client.get(f"/api/v1/exports/{export_id}/inventory")

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
