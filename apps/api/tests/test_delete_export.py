"""`DELETE /exports/{id}` (spec 06, tercera ronda de M3).

El matiz central: en modo subida el directorio de trabajo ENTERO es nuestro (se borra
completo); en modo local la carpeta es del USUARIO (solo se borra `_output/`, nunca
el export original) - ver decisiones en `services/lifecycle.py`.
"""

from __future__ import annotations

import io
import shutil
import sys
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_export_md_api.main import app
from claude_export_md_api.services import exports as exports_service
from claude_export_md_api.services import jobs as jobs_service
from claude_export_md_api.services import lifecycle as lifecycle_service

PROBLEM_JSON = "application/problem+json"


@pytest.fixture(autouse=True)
def _reset_stores() -> Iterator[None]:
    jobs_service.get_job_store()._jobs.clear()  # type: ignore[attr-defined]
    yield
    exports_service.get_store()._records.clear()  # type: ignore[attr-defined]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _wait_for_terminal_status(
    client: TestClient, job_id: str, timeout_s: float = 10.0
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} no termino en {timeout_s}s")


def _legacy_export_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("conversations.json", b"[]")
        zf.writestr("projects.json", b"[]")
        zf.writestr("users.json", b"{}")
    return buffer.getvalue()


def test_delete_of_an_uploaded_export_removes_the_whole_work_directory(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/exports",
        files=[("files", ("export.zip", _legacy_export_zip(), "application/zip"))],
    )
    export_id = created.json()["export_id"]
    work_dir = exports_service.export_directory(export_id)
    assert work_dir.is_dir()

    response = client.delete(f"/api/v1/exports/{export_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert not work_dir.exists()
    # El registro tambien se olvido: /inventory sobre el mismo id vuelve a ser 404.
    follow_up = client.get(f"/api/v1/exports/{export_id}/inventory")
    assert follow_up.status_code == 404


def test_delete_of_a_local_export_keeps_the_users_original_folder(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, synthetic_export_dir: Path
) -> None:
    monkeypatch.setenv("CEM_ALLOW_LOCAL_PATHS", "true")
    users_folder = tmp_path / "carpeta-del-usuario"
    shutil.copytree(synthetic_export_dir, users_folder)

    created = client.post("/api/v1/exports", json={"path": str(users_folder)})
    export_id = created.json()["export_id"]

    convert_response = client.post(f"/api/v1/exports/{export_id}/convert")
    job_id = convert_response.json()["job_id"]
    _wait_for_terminal_status(client, job_id)
    output_dir = users_folder / "_output"
    assert output_dir.is_dir()

    response = client.delete(f"/api/v1/exports/{export_id}")

    assert response.status_code == 204
    # La carpeta del USUARIO sigue entera, con su contenido original.
    assert users_folder.is_dir()
    assert (users_folder / "conversations-000" / "conversations.json").exists()
    assert (users_folder / "memories-000" / "profile.md").exists()
    # Solo lo que nosotros creamos ahi (_output/) desaparecio.
    assert not output_dir.exists()


def test_delete_of_a_local_export_that_was_never_converted_does_not_touch_the_folder(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, synthetic_export_dir: Path
) -> None:
    monkeypatch.setenv("CEM_ALLOW_LOCAL_PATHS", "true")
    users_folder = tmp_path / "carpeta-del-usuario"
    shutil.copytree(synthetic_export_dir, users_folder)

    created = client.post("/api/v1/exports", json={"path": str(users_folder)})
    export_id = created.json()["export_id"]

    response = client.delete(f"/api/v1/exports/{export_id}")

    assert response.status_code == 204
    assert users_folder.is_dir()
    assert (users_folder / "conversations-000" / "conversations.json").exists()


def test_delete_also_forgets_jobs_of_that_export(client: TestClient) -> None:
    created = client.post(
        "/api/v1/exports",
        files=[("files", ("export.zip", _legacy_export_zip(), "application/zip"))],
    )
    export_id = created.json()["export_id"]
    convert_response = client.post(f"/api/v1/exports/{export_id}/convert")
    job_id = convert_response.json()["job_id"]
    _wait_for_terminal_status(client, job_id)

    client.delete(f"/api/v1/exports/{export_id}")

    follow_up = client.get(f"/api/v1/jobs/{job_id}")
    assert follow_up.status_code == 404


def test_delete_while_a_conversion_is_in_progress_is_rejected_with_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Observacion 2 de la revision de M3: sin este chequeo, `DELETE` borraba el
    registro con `204` pero el thread de conversion en curso seguia escribiendo y
    RECREABA `_output/` despues del borrado (reproducido por el reviewer)."""
    real_convert = jobs_service.run_convert

    def slow_convert(*args: object, **kwargs: object) -> object:
        time.sleep(0.5)
        return real_convert(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(jobs_service, "run_convert", slow_convert)

    created = client.post(
        "/api/v1/exports",
        files=[("files", ("export.zip", _legacy_export_zip(), "application/zip"))],
    )
    export_id = created.json()["export_id"]
    convert_response = client.post(f"/api/v1/exports/{export_id}/convert")
    job_id = convert_response.json()["job_id"]

    response = client.delete(f"/api/v1/exports/{export_id}")

    assert response.status_code == 409
    assert response.headers["content-type"] == PROBLEM_JSON
    assert job_id in response.json()["detail"]

    # La conversion sigue sola en segundo plano: se espera a que termine y se limpia
    # de verdad, para no dejar directorios de trabajo huerfanos mas alla del test.
    _wait_for_terminal_status(client, job_id)
    cleanup = client.delete(f"/api/v1/exports/{export_id}")
    assert cleanup.status_code == 204


def test_delete_is_allowed_again_once_the_job_reached_a_terminal_status(
    client: TestClient,
) -> None:
    """El chequeo del test de arriba no debe volverse una prohibicion permanente:
    una vez que el job llega a `done`/`failed`, `DELETE` vuelve a aceptarse."""
    created = client.post(
        "/api/v1/exports",
        files=[("files", ("export.zip", _legacy_export_zip(), "application/zip"))],
    )
    export_id = created.json()["export_id"]
    convert_response = client.post(f"/api/v1/exports/{export_id}/convert")
    job_id = convert_response.json()["job_id"]
    _wait_for_terminal_status(client, job_id)

    response = client.delete(f"/api/v1/exports/{export_id}")

    assert response.status_code == 204


def test_delete_of_an_unknown_export_id_is_404(client: TestClient) -> None:
    response = client.delete("/api/v1/exports/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON


def test_delete_is_not_idempotent_a_second_call_is_also_404(client: TestClient) -> None:
    """Decision propia (spec 06 no lo aclara): consistente con el resto de la API,
    un `export_id` que no existe -> 404, tambien en la segunda llamada."""
    created = client.post(
        "/api/v1/exports",
        files=[("files", ("export.zip", _legacy_export_zip(), "application/zip"))],
    )
    export_id = created.json()["export_id"]

    first = client.delete(f"/api/v1/exports/{export_id}")
    second = client.delete(f"/api/v1/exports/{export_id}")

    assert first.status_code == 204
    assert second.status_code == 404


# ---------------------------------------------------------------------------
# bug 1, parte 4 (3ra ronda de M3): el borrado ya no es 100% silencioso del lado
# del servidor cuando un archivo no se puede quitar (el hilo cem-zip-writer de
# services/output.py podia dejarlo abierto tras un abort duro).
# ---------------------------------------------------------------------------


def test_rmtree_best_effort_logs_a_warning_for_each_failure_instead_of_swallowing_it(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reproduce el bug SIN depender de un locking de archivos real (que se comporta
    distinto entre Windows/Linux): se reemplaza `shutil.rmtree` por un doble que
    simula la firma real de `onexc` (Python 3.12+) invocandolo con un fallo sintetico,
    y se confirma que `_rmtree_best_effort` (a) no lo deja escapar como excepcion
    (mismo contrato que `ignore_errors=True`) y (b) lo deja anotado con
    `logger.warning` en vez de tragarlo en silencio."""

    def fake_rmtree(path: Path, *, onexc: object = None, **_kwargs: object) -> None:
        assert onexc is not None, "se esperaba que _rmtree_best_effort pasara onexc"
        onexc(  # type: ignore[misc]
            "unlink", str(path / "locked.txt"), PermissionError("archivo en uso")
        )

    monkeypatch.setattr(lifecycle_service.shutil, "rmtree", fake_rmtree)

    with caplog.at_level("WARNING"):
        lifecycle_service._rmtree_best_effort(tmp_path)  # no debe lanzar

    warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any("locked.txt" in message for message in warnings)


@pytest.mark.skipif(sys.platform != "win32", reason="depende del locking de archivos de Windows")
def test_delete_of_an_uploaded_export_logs_when_a_locked_file_survives_the_rmtree(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Confirmacion end-to-end (no solo el doble de arriba) en esta plataforma real:
    un archivo abierto sin compartir borrado (el default de `open()` en Windows, el
    mismo SO donde el reviewer reprodujo el bug contra un uvicorn real) sobrevive al
    `shutil.rmtree`, y ahora eso queda registrado en vez de perderse en silencio -
    aunque el `DELETE` siga respondiendo 204 (el contrato publicado no cambia)."""
    created = client.post(
        "/api/v1/exports",
        files=[("files", ("export.zip", _legacy_export_zip(), "application/zip"))],
    )
    export_id = created.json()["export_id"]
    work_dir = exports_service.export_directory(export_id)
    locked_file = work_dir / "export.zip"

    handle = locked_file.open("rb")
    try:
        with caplog.at_level("WARNING"):
            response = client.delete(f"/api/v1/exports/{export_id}")
        assert response.status_code == 204
        warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert any("export.zip" in message for message in warnings)
        # El registro se olvido igual (el contrato del DELETE no cambia).
        follow_up = client.get(f"/api/v1/exports/{export_id}/inventory")
        assert follow_up.status_code == 404
    finally:
        handle.close()
        shutil.rmtree(work_dir, ignore_errors=True)
