"""`POST /exports/{id}/convert`, `GET /jobs/{id}` y `GET /jobs/{id}/events` (spec 06,
segunda ronda de M3, CA-2, CA-3, CA-6).

Usa el fixture sintetico completo de core (`synthetic_export_dir`, conftest.py) pero
SIEMPRE sobre una COPIA en `tmp_path`: a diferencia de `/inventory` (solo lectura),
`/convert` escribe un `_output/` dentro del directorio del export (services/jobs.py),
y ese fixture vive en el repo real -> escribir ahi ensuciaria packages/core/tests.

Importante sobre `TestClient`: la conversion corre en una tarea de `asyncio` de fondo
(`services/jobs.py::start_conversion`), lanzada DURANTE el request de `POST /convert`.
`TestClient` solo mantiene vivo su "portal" (el hilo con el event loop de la app)
mientras se lo usa como context manager (`with TestClient(app) as client:`); sin el
`with`, cada llamada abre y cierra su propio portal, y una tarea de fondo que todavia
no termino cuando la respuesta ya se mando queda huerfana (su hilo de conversion sigue
corriendo, pero nadie vuelve a resumir la corrutina que esperaba el resultado). Por
eso TODOS los tests de este archivo usan un unico `client` de este tipo de punta a
punta, registrado como fixture.
"""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_export_md_api.main import app
from claude_export_md_api.services import jobs as jobs_service

PROBLEM_JSON = "application/problem+json"

#: Conteos deterministas del fixture sintetico completo (verificados corriendo
#: `convert()` directo sobre el fixture: ver el resumen de la tarea).
EXPECTED_COUNTS = {"conversations": 2, "projects": 2}
EXPECTED_ERROR_COUNT = 3
EXPECTED_WARNING_COUNT = 5
#: Las 5 categorias que `convert()` procesa (usecases/convert.py de core): todas
#: emiten progreso, aunque algunas terminen en 0 items (el fixture tiene entradas
#: invalidas a proposito en memories/light_metadata/frames, de ahi los errores).
ALL_CATEGORIES = {"memories", "light_metadata", "projects", "conversations", "frames"}


@pytest.fixture(autouse=True)
def _reset_job_store() -> Iterator[None]:
    """Los tests de este archivo comparten el `JobStore` modulo-singleton: se limpia
    entre tests para que uno no vea los jobs de otro."""
    jobs_service.get_job_store()._jobs.clear()  # type: ignore[attr-defined]
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Un unico `TestClient` de punta a punta (ver docstring del modulo)."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def local_export_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    synthetic_export_dir: Path,
) -> str:
    """Registra en modo local una COPIA del fixture sintetico (nunca el original)."""
    monkeypatch.setenv("CEM_ALLOW_LOCAL_PATHS", "true")
    copy = tmp_path / "mi-export"
    shutil.copytree(synthetic_export_dir, copy)
    created = client.post("/api/v1/exports", json={"path": str(copy)})
    assert created.status_code == 201
    export_id: str = created.json()["export_id"]
    return export_id


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


def test_convert_responds_before_the_conversion_finishes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, local_export_id: str
) -> None:
    """CA-2: la respuesta llega en <200ms aunque la conversion tarde mas."""
    real_convert = jobs_service.run_convert

    def slow_convert(*args: object, **kwargs: object) -> object:
        time.sleep(0.3)
        return real_convert(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(jobs_service, "run_convert", slow_convert)

    started = time.monotonic()
    response = client.post(f"/api/v1/exports/{local_export_id}/convert")
    elapsed = time.monotonic() - started

    assert response.status_code == 202
    assert elapsed < 0.2, f"la respuesta tardo {elapsed:.3f}s (deberia ser inmediata)"
    body = response.json()
    assert isinstance(body["job_id"], str) and body["job_id"]

    # La conversion real (lenta a proposito) sigue en marcha en segundo plano: se
    # espera a que termine para no dejarla colgada mas alla del test.
    _wait_for_terminal_status(client, body["job_id"])


def test_job_reaches_done_with_the_fixtures_counts(
    client: TestClient, local_export_id: str
) -> None:
    """CA-3: progreso por categoria + estado final con conteos coherentes."""
    response = client.post(f"/api/v1/exports/{local_export_id}/convert")
    job_id = response.json()["job_id"]

    body = _wait_for_terminal_status(client, job_id)

    assert body["status"] == "done"
    assert body["counts"] == EXPECTED_COUNTS
    assert body["errors"] == EXPECTED_ERROR_COUNT
    assert body["warnings"] == EXPECTED_WARNING_COUNT
    assert body["reason"] is None
    categories_seen = {event["category"] for event in body["progress"]}
    assert ALL_CATEGORIES <= categories_seen


def test_job_status_transitions_through_pending_or_running_before_done(
    client: TestClient, local_export_id: str
) -> None:
    response = client.post(f"/api/v1/exports/{local_export_id}/convert")
    job_id = response.json()["job_id"]

    first = client.get(f"/api/v1/jobs/{job_id}")
    assert first.status_code == 200
    assert first.json()["status"] in ("pending", "running", "done")

    _wait_for_terminal_status(client, job_id)


def test_events_stream_emits_progress_and_a_final_done(
    client: TestClient, local_export_id: str
) -> None:
    """CA-3: SSE con al menos un `progress` y un `done` final."""
    created = client.post(f"/api/v1/exports/{local_export_id}/convert")
    job_id = created.json()["job_id"]

    progress_events: list[dict[str, object]] = []
    final_event: str | None = None
    final_payload: dict[str, object] = {}
    with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        current_event = "message"
        for line in response.iter_lines():
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                payload = json.loads(line.split(":", 1)[1].strip())
                if current_event == "progress":
                    progress_events.append(payload)
                elif current_event in ("done", "error"):
                    final_event = current_event
                    final_payload = payload
                    break

    assert progress_events, "se esperaba al menos un evento 'progress'"
    assert {e["category"] for e in progress_events} & ALL_CATEGORIES
    assert final_event == "done"
    assert final_payload["counts"] == EXPECTED_COUNTS
    assert final_payload["errors"] == EXPECTED_ERROR_COUNT


def test_events_final_done_payload_never_leaks_the_server_side_destination_path(
    client: TestClient, local_export_id: str
) -> None:
    """Observacion 3 de la revision de M3: `GET /jobs/{id}` (JobStatusResponse) NO
    expone `destination` (una ruta absoluta del servidor) a proposito, pero el evento
    SSE `done` si lo mandaba - inconsistente, y una fuga de la estructura de
    directorios interna del servidor hacia cualquier cliente."""
    created = client.post(f"/api/v1/exports/{local_export_id}/convert")
    job_id = created.json()["job_id"]

    final_payload: dict[str, object] = {}
    with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as response:
        current_event = "message"
        for line in response.iter_lines():
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                payload = json.loads(line.split(":", 1)[1].strip())
                if current_event == "done":
                    final_payload = payload
                    break

    assert final_payload, "se esperaba un evento 'done'"
    assert "destination" not in final_payload


def test_events_of_an_already_finished_job_returns_final_state_immediately(
    client: TestClient, local_export_id: str
) -> None:
    """Job ya terminado cuando alguien se conecta -> el estado final de una, sin colgarse."""
    created = client.post(f"/api/v1/exports/{local_export_id}/convert")
    job_id = created.json()["job_id"]
    _wait_for_terminal_status(client, job_id)

    started = time.monotonic()
    with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        lines = list(response.iter_lines())
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, "deberia cerrar de inmediato, no esperar eventos nuevos"
    assert any(line.strip() == "event: done" for line in lines)


def test_job_timeout_marks_the_job_as_failed_with_reason_timeout(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, local_export_id: str
) -> None:
    """CA-6: `CEM_JOB_TIMEOUT_S` muy bajo -> `failed` con motivo `timeout`."""
    monkeypatch.setenv("CEM_JOB_TIMEOUT_S", "0")

    response = client.post(f"/api/v1/exports/{local_export_id}/convert")
    job_id = response.json()["job_id"]

    body = _wait_for_terminal_status(client, job_id)

    assert body["status"] == "failed"
    assert body["reason"] == "timeout"


def test_only_field_is_accepted_but_has_no_effect_yet(
    client: TestClient, local_export_id: str
) -> None:
    """`only` esta en el spec pero core todavia no filtra: se acepta y se ignora."""
    response = client.post(
        f"/api/v1/exports/{local_export_id}/convert", json={"only": ["memories"]}
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    body = _wait_for_terminal_status(client, job_id)

    # Se ignora de verdad: las conversaciones y proyectos igual se convirtieron.
    assert body["status"] == "done"
    assert body["counts"] == EXPECTED_COUNTS


def test_a_second_convert_while_one_is_still_running_is_409_with_the_existing_job_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, local_export_id: str
) -> None:
    """Observacion 1 de la revision de M3: sin este chequeo, 3 `POST /convert`
    seguidos sobre el MISMO export (reproducido por el reviewer) lanzaban 3 jobs que
    escribian CONCURRENTEMENTE el mismo `_output/`."""
    real_convert = jobs_service.run_convert

    def slow_convert(*args: object, **kwargs: object) -> object:
        time.sleep(0.5)
        return real_convert(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(jobs_service, "run_convert", slow_convert)

    first = client.post(f"/api/v1/exports/{local_export_id}/convert")
    assert first.status_code == 202
    first_job_id = first.json()["job_id"]

    second = client.post(f"/api/v1/exports/{local_export_id}/convert")

    assert second.status_code == 409
    assert second.headers["content-type"] == PROBLEM_JSON
    assert first_job_id in second.json()["detail"]

    # La conversion original sigue en marcha en segundo plano: se espera a que
    # termine para no dejarla colgada mas alla del test.
    _wait_for_terminal_status(client, first_job_id)


def test_convert_is_allowed_again_once_the_previous_job_reached_a_terminal_status(
    client: TestClient, local_export_id: str
) -> None:
    """El chequeo del test de arriba no debe volverse una prohibicion permanente:
    una vez que el job anterior llega a `done`/`failed`, un nuevo `POST /convert`
    sobre el mismo export vuelve a aceptarse normalmente."""
    first = client.post(f"/api/v1/exports/{local_export_id}/convert")
    _wait_for_terminal_status(client, first.json()["job_id"])

    second = client.post(f"/api/v1/exports/{local_export_id}/convert")

    assert second.status_code == 202
    _wait_for_terminal_status(client, second.json()["job_id"])


def test_convert_of_an_unknown_export_id_is_404(client: TestClient) -> None:
    response = client.post("/api/v1/exports/does-not-exist/convert")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON


def test_job_status_of_an_unknown_job_id_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/jobs/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON


def test_job_events_of_an_unknown_job_id_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/jobs/does-not-exist/events")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON


# ---------------------------------------------------------------------------
# bug 2 (3ra ronda de M3): "activo" no puede ser solo el ESTADO del job. Cuando un
# job vence por timeout, el hilo REAL de `asyncio.to_thread(run_sync)` sigue
# escribiendo en `_output/` en segundo plano (no se puede matar, limitacion de
# Python) - los guards de la ronda anterior (`find_active_job_id`,
# `create_if_no_active_job`) solo miraban `pending`/`running`, asi que un job
# `failed`/`timeout` dejaba de contar como activo aunque su hilo siguiera vivo.
# ---------------------------------------------------------------------------


def test_job_store_a_timed_out_job_is_still_active_until_its_finished_event_fires() -> None:
    """Test unitario, deterministico, sin threads ni timing real: reproduce el bug
    directo sobre `JobStore`. Antes del fix, `find_active_job_id` miraba solo
    `job.status in ("pending", "running")`, asi que un job `failed` (por el motivo
    que sea) NUNCA contaba como activo - ni siquiera si su hilo real seguia vivo."""
    store = jobs_service.JobStore()
    store.create("job-1", "export-1")
    store.mark_failed("job-1", jobs_service.TIMEOUT_REASON)

    # El job ya esta `failed`, pero su hilo real "sigue vivo" (finished_event sin
    # activar): todavia debe contar como activo.
    assert store.find_active_job_id("export-1") == "job-1"
    assert store.create_if_no_active_job("job-2", "export-1") == "job-1"

    finished_event = store.get_finished_event("job-1")
    assert finished_event is not None
    assert not finished_event.is_set()

    # Recien cuando el hilo real termina de verdad (finished_event.set(), que en
    # produccion pasa en el `finally` de `run_sync`) el job deja de bloquear.
    finished_event.set()

    assert store.find_active_job_id("export-1") is None
    assert store.create_if_no_active_job("job-2", "export-1") is None


def test_job_store_a_job_failed_for_a_reason_other_than_timeout_is_never_active() -> None:
    """Un `failed` normal (no timeout) no tiene ningun hilo real corriendo detras -
    nunca debe contar como activo, tenga o no `finished_event` seteado."""
    store = jobs_service.JobStore()
    store.create("job-1", "export-1")
    store.mark_failed("job-1", "algun error real de parseo")

    assert store.find_active_job_id("export-1") is None


def test_job_store_a_pending_or_running_job_is_active_regardless_of_finished_event() -> None:
    """El caso ya cubierto por la ronda anterior no debe romperse: un job
    `pending`/`running` sigue siendo activo aunque nadie haya tocado su
    `finished_event` (nunca se activa mientras el hilo sigue corriendo de verdad)."""
    store = jobs_service.JobStore()
    store.create("job-1", "export-1")

    assert store.find_active_job_id("export-1") == "job-1"

    store.mark_running("job-1")

    assert store.find_active_job_id("export-1") == "job-1"


def test_timed_out_job_still_blocks_convert_and_delete_until_the_real_thread_finishes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, local_export_id: str
) -> None:
    """Confirmacion end-to-end (spec 06): con `run_convert` deliberadamente mas lento
    que `CEM_JOB_TIMEOUT_S`, justo DESPUES de que el job se marque `failed`/`timeout`
    (mientras el hilo real todavia esta corriendo) tanto un nuevo `POST /convert` como
    `DELETE` deben seguir dando `409` - y solo dejan de hacerlo una vez que el hilo
    real termina de verdad (se espera a `finished_event`, nunca un sleep arbitrario)."""
    real_convert = jobs_service.run_convert

    def slow_convert(*args: object, **kwargs: object) -> object:
        time.sleep(0.6)
        return real_convert(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(jobs_service, "run_convert", slow_convert)
    monkeypatch.setenv("CEM_JOB_TIMEOUT_S", "0.05")

    response = client.post(f"/api/v1/exports/{local_export_id}/convert")
    job_id = response.json()["job_id"]

    body = _wait_for_terminal_status(client, job_id)
    assert body["status"] == "failed"
    assert body["reason"] == "timeout"

    finished_event = jobs_service.get_job_store().get_finished_event(job_id)
    assert finished_event is not None
    assert not finished_event.is_set(), "el hilo real todavia deberia seguir corriendo"

    second_convert = client.post(f"/api/v1/exports/{local_export_id}/convert")
    assert second_convert.status_code == 409
    assert second_convert.headers["content-type"] == PROBLEM_JSON

    delete_response = client.delete(f"/api/v1/exports/{local_export_id}")
    assert delete_response.status_code == 409
    assert delete_response.headers["content-type"] == PROBLEM_JSON

    assert finished_event.wait(timeout=10.0), "el hilo real no termino a tiempo"

    third_convert = client.post(f"/api/v1/exports/{local_export_id}/convert")
    assert third_convert.status_code == 202
    _wait_for_terminal_status(client, third_convert.json()["job_id"])
