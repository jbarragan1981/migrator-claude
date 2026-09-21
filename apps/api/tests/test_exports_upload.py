"""`POST /api/v1/exports` en modo subida multipart, spec 06 CA-1/CA-5."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_export_md_api.main import app
from claude_export_md_api.services import exports as exports_service

PROBLEM_JSON = "application/problem+json"


def _zip_of(*files: tuple[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files:
            zf.writestr(name, content)
    return buffer.getvalue()


def _legacy_export_zip() -> bytes:
    """Un unico .zip con la forma legacy (conversations/projects/users.json en la raiz)."""
    return _zip_of(
        ("conversations.json", b"[]"),
        ("projects.json", b"[]"),
        ("users.json", b"{}"),
    )


def test_a_valid_upload_is_registered() -> None:
    client = TestClient(app)
    zip_bytes = _legacy_export_zip()

    response = client.post(
        "/api/v1/exports",
        files=[("files", ("export.zip", zip_bytes, "application/zip"))],
    )

    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["export_id"], str) and body["export_id"]


def test_a_valid_upload_can_be_inventoried_end_to_end() -> None:
    client = TestClient(app)
    zip_bytes = _legacy_export_zip()

    created = client.post(
        "/api/v1/exports",
        files=[("files", ("export.zip", zip_bytes, "application/zip"))],
    )
    export_id = created.json()["export_id"]

    response = client.get(f"/api/v1/exports/{export_id}/inventory")

    assert response.status_code == 200
    body = response.json()
    assert body["format_version"] == "legacy-single-zip"
    assert {"conversations", "projects", "users"} <= set(body["categories"])


def test_multiple_files_can_be_uploaded_together() -> None:
    """Caso real del README: TODAS las partes comparten `name="file"`.

    `Starlette.Request.form()` es un `FormData` tipo multidict: `.values()` deduplica
    por nombre de campo y solo deja sobrevivir la ULTIMA parte con ese nombre. Este es
    exactamente el escenario del ejemplo de curl del README (tres `-F "file=@..."`) -
    si `register_upload` iterara con `.values()` en vez de `.multi_items()`, esta subida
    perderia 2 de los 3 archivos con un 201 (bug silencioso, sin ningun aviso al cliente).
    """
    client = TestClient(app)
    manifest = b'{"data_files": []}'
    conversations_zip = _zip_of(("conversations.json", b"[]"))
    memories_zip = _zip_of(("profile.md", b"# perfil"))

    response = client.post(
        "/api/v1/exports",
        files=[
            ("file", ("conversations-000.zip", conversations_zip, "application/zip")),
            ("file", ("memories-000.zip", memories_zip, "application/zip")),
            ("file", ("member-manifest-20260101.json", manifest, "application/json")),
        ],
    )

    assert response.status_code == 201
    export_id = response.json()["export_id"]
    work_dir = exports_service.export_directory(export_id)
    assert sorted(p.name for p in work_dir.iterdir()) == [
        "conversations-000.zip",
        "member-manifest-20260101.json",
        "memories-000.zip",
    ]


def test_a_path_traversal_filename_is_rejected_before_writing_anything(
    tmp_path: Path,
) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/exports",
        files=[("files", ("../../etc/passwd", b"malicious", "application/octet-stream"))],
    )

    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM_JSON
    work_dir = tmp_path / "work"
    # El fixture autouse ya fijo CEM_WORK_DIR a tmp_path/work; nada debe haberse creado ahi.
    assert not work_dir.exists() or list(work_dir.iterdir()) == []


def test_a_backslash_path_traversal_filename_is_rejected() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/exports",
        files=[("files", ("..\\..\\windows\\win.ini", b"malicious", "application/octet-stream"))],
    )

    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM_JSON


def test_an_upload_over_the_configured_limit_is_rejected_with_413(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CEM_MAX_UPLOAD_MB", "1")
    client = TestClient(app)
    too_big = b"0" * (2 * 1024 * 1024)  # 2 MiB > 1 MiB limit

    response = client.post(
        "/api/v1/exports",
        files=[("files", ("huge.zip", too_big, "application/zip"))],
    )

    assert response.status_code == 413
    assert response.headers["content-type"] == PROBLEM_JSON


def test_an_empty_upload_is_rejected() -> None:
    client = TestClient(app)

    response = client.post("/api/v1/exports", files=[])

    assert response.status_code in (400, 415, 422)
