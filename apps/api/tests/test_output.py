"""`GET /exports/{id}/output/tree`, `GET /exports/{id}/output/file` y
`GET /exports/{id}/download` (spec 06, CA-4; `/download` en su diseno de la cuarta
ronda de fixes de M3, ver STATUS.md).

Igual que `test_convert_jobs.py`: usa SIEMPRE una COPIA del fixture sintetico en
`tmp_path` (nunca el original del repo), y un unico `TestClient` de punta a punta
(el context manager mantiene vivo el "portal" que necesita la tarea de fondo de
`POST /convert`; ver docstring de test_convert_jobs.py).
"""

from __future__ import annotations

import io
import shutil
import tempfile
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_export_md_api.main import app
from claude_export_md_api.services import jobs as jobs_service
from claude_export_md_api.services import output as output_service

PROBLEM_JSON = "application/problem+json"


@pytest.fixture(autouse=True)
def _reset_job_store() -> Iterator[None]:
    jobs_service.get_job_store()._jobs.clear()  # type: ignore[attr-defined]
    yield


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


@pytest.fixture
def converted_export_id(client: TestClient, local_export_id: str) -> str:
    """Un export local ya convertido (job en 'done')."""
    response = client.post(f"/api/v1/exports/{local_export_id}/convert")
    job_id = response.json()["job_id"]
    _wait_for_terminal_status(client, job_id)
    return local_export_id


# ---------------------------------------------------------------------------
# /output/tree
# ---------------------------------------------------------------------------


def test_tree_of_a_converted_export_matches_what_convert_wrote(
    client: TestClient, converted_export_id: str, tmp_path: Path
) -> None:
    response = client.get(f"/api/v1/exports/{converted_export_id}/output/tree")

    assert response.status_code == 200
    body = response.json()
    entries = {entry["path"]: entry for entry in body["entries"]}

    # Archivos que `convert()` siempre escribe (README/_index/_report), + al menos
    # una carpeta de cada categoria del fixture sintetico completo.
    assert "README.md" in entries
    assert entries["README.md"]["kind"] == "file"
    assert entries["README.md"]["size"] > 0
    assert "_index.md" in entries
    assert "_report" in entries and entries["_report"]["kind"] == "dir"
    assert "_report/summary.json" in entries
    # El fixture sintetico completo (conftest.py) SOLO produce items validos en
    # conversations y projects (memories/light_metadata/frames traen entradas
    # invalidas a proposito, ver test_convert_jobs.py::EXPECTED_COUNTS).
    assert any(path.startswith("conversations") for path in entries)
    assert any(path.startswith("projects") for path in entries)

    # Ninguna entrada de carpeta trae tamano.
    for entry in body["entries"]:
        if entry["kind"] == "dir":
            assert entry["size"] is None


def test_tree_is_deterministic_across_calls(client: TestClient, converted_export_id: str) -> None:
    first = client.get(f"/api/v1/exports/{converted_export_id}/output/tree").json()
    second = client.get(f"/api/v1/exports/{converted_export_id}/output/tree").json()

    assert first == second
    paths = [entry["path"] for entry in first["entries"]]
    assert paths == sorted(paths)


def test_tree_of_an_export_never_converted_is_404_with_a_distinct_detail(
    client: TestClient, local_export_id: str
) -> None:
    response = client.get(f"/api/v1/exports/{local_export_id}/output/tree")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert "convert" in response.json()["detail"].lower()


def test_tree_of_an_unknown_export_id_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/exports/does-not-exist/output/tree")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON


# ---------------------------------------------------------------------------
# /output/file
# ---------------------------------------------------------------------------


def test_file_returns_the_real_content_of_a_tree_entry(
    client: TestClient, converted_export_id: str
) -> None:
    tree = client.get(f"/api/v1/exports/{converted_export_id}/output/tree").json()
    readme_path = next(e["path"] for e in tree["entries"] if e["path"] == "README.md")

    response = client.get(
        f"/api/v1/exports/{converted_export_id}/output/file", params={"path": readme_path}
    )

    assert response.status_code == 200
    assert "markdown" in response.headers["content-type"]
    assert len(response.content) > 0

    # Comparado con lo que de verdad hay en disco (via el propio directorio de
    # trabajo, sin pasar por la API), para probar que el contenido es el correcto.
    output_dir = _output_dir_of(client, converted_export_id)
    assert response.content == (output_dir / "README.md").read_bytes()


def test_file_inside_a_subdirectory_works_with_forward_slashes(
    client: TestClient, converted_export_id: str
) -> None:
    tree = client.get(f"/api/v1/exports/{converted_export_id}/output/tree").json()
    a_conversation = next(
        e["path"]
        for e in tree["entries"]
        if e["kind"] == "file"
        and e["path"].startswith("conversations/")
        and e["path"].endswith(".md")
    )

    response = client.get(
        f"/api/v1/exports/{converted_export_id}/output/file", params={"path": a_conversation}
    )

    assert response.status_code == 200
    assert len(response.content) > 0


@pytest.mark.parametrize(
    "malicious_path",
    [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\win.ini",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "conversations/../../../etc/passwd",
    ],
)
def test_path_traversal_is_rejected_with_400_before_reading_anything(
    client: TestClient, converted_export_id: str, malicious_path: str
) -> None:
    response = client.get(
        f"/api/v1/exports/{converted_export_id}/output/file", params={"path": malicious_path}
    )

    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM_JSON
    # CA-4: nada del contenido "sensible" se filtro en la respuesta.
    assert b"root:" not in response.content
    assert b"[fonts]" not in response.content


@pytest.mark.parametrize(
    "control_char_path",
    [
        "_index.md\x00.txt",  # NUL: reproduce el 500 crudo de bloqueante 4
        "_index.md\x01.txt",  # otro caracter de control ASCII, mismo rechazo
        "_index.md\n.txt",
    ],
)
def test_a_path_with_a_control_character_is_rejected_with_400_never_500(
    client: TestClient, converted_export_id: str, control_char_path: str
) -> None:
    """Bloqueante 4: `Path.resolve()` sobre un string con un byte NUL lanza
    `ValueError: embedded null character in path`, que ningun exception handler
    atrapaba - eso rompia el contrato RFC 7807 (`content-type: text/plain`, 500 crudo
    de Starlette) en vez de devolver un `application/problem+json` como CUALQUIER
    otro error de esta API. `_validate_relative_path` debe rechazar el caracter de
    control ANTES de construir ningun `Path` (mismo criterio que ya usa para `..`)."""
    response = client.get(
        f"/api/v1/exports/{converted_export_id}/output/file",
        params={"path": control_char_path},
    )

    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM_JSON


def test_a_path_that_does_not_exist_in_the_tree_is_404(
    client: TestClient, converted_export_id: str
) -> None:
    response = client.get(
        f"/api/v1/exports/{converted_export_id}/output/file",
        params={"path": "no-such-file.md"},
    )

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON


def test_file_without_a_path_parameter_is_400(client: TestClient, converted_export_id: str) -> None:
    response = client.get(f"/api/v1/exports/{converted_export_id}/output/file")

    assert response.status_code in (400, 422)


def test_file_of_an_export_never_converted_is_404(client: TestClient, local_export_id: str) -> None:
    response = client.get(
        f"/api/v1/exports/{local_export_id}/output/file", params={"path": "README.md"}
    )

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON


# ---------------------------------------------------------------------------
# /download
# ---------------------------------------------------------------------------


def test_download_zip_contains_the_expected_files(
    client: TestClient, converted_export_id: str
) -> None:
    tree = client.get(f"/api/v1/exports/{converted_export_id}/output/tree").json()
    expected_files = {e["path"] for e in tree["entries"] if e["kind"] == "file"}

    response = client.get(f"/api/v1/exports/{converted_export_id}/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert zf.testzip() is None  # ningun miembro corrupto
        names = set(zf.namelist())
        assert expected_files <= names
        readme_bytes = zf.read("README.md")

    output_dir = _output_dir_of(client, converted_export_id)
    assert readme_bytes == (output_dir / "README.md").read_bytes()


def test_download_of_an_export_never_converted_is_404(
    client: TestClient, local_export_id: str
) -> None:
    response = client.get(f"/api/v1/exports/{local_export_id}/download")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON


def test_download_of_an_unknown_export_id_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/exports/does-not-exist/download")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON


# ---------------------------------------------------------------------------
# /download: limpieza del temporal (cuarta ronda de fixes de M3 - ver STATUS.md)
#
# El mecanismo viejo (hilo productor + queue.Queue) fue RECHAZADO tres veces por el
# revisor, la ultima por un bug de fondo (un abort duro del cliente podia dejar el
# hilo productor colgado para siempre en queue.put(), agotando el pool de
# asyncio.to_thread compartido con las conversiones) y por throughput real de solo
# ~42 KB/s. El diseno nuevo (services/output.py::build_zip_archive +
# routers/output.py::download_export) arma el zip COMPLETO en un temporal dentro de
# un UNICO asyncio.to_thread y lo sirve con TempZipResponse (services/output.py) - NO
# con FileResponse + BackgroundTask (quinta ronda: ver el bloque de comentarios de
# abajo, FileResponse.__call__ no corre background para un Range invalido).
#
# Confirmacion de que el temporal SIEMPRE se borra, incluso si el cliente corta la
# descarga a mitad de camino: no es practico simular un corte real de conexion con
# `TestClient` (su transporte ASGI corre la app COMPLETA en un portal sincrono antes
# de devolver la respuesta - lo confirma `starlette.testclient._TestClientTransport
# .handle_request`, que bloquea hasta `response_complete.wait()` sin importar si el
# test despues lee `response.content` o no). Se confirmo leyendo el codigo real que
# corre en produccion:
#   - `uvicorn.protocols.http.h11_impl.RequestResponseCycle.send` (y el equivalente en
#     `httptools_impl.py`) empieza con `if self.disconnected: return` - si el cliente
#     ya se fue, cada `await send(...)` es un NO-OP que vuelve de inmediato, nunca una
#     excepcion; el envio termina "normal" pase lo que pase con la conexion.
#   - PERO `starlette.responses.FileResponse.__call__` NO llega siempre a
#     `await self.background()`: `except MalformedRangeHeader` y
#     `except RangeNotSatisfiable` devuelven una `PlainTextResponse` propia (400/416)
#     con un `return` que SALTEA esa linea (quinta ronda de revision de M3, reproducido
#     con un `Range` invalido dejando el temporal huerfano). Por eso `download_export`
#     sirve el zip con `TempZipResponse` (services/output.py) en vez de
#     `FileResponse(..., background=...)`: el borrado vive en un `finally` propio que
#     cubre el camino normal Y esos dos `return` tempranos de `Range`.
# ---------------------------------------------------------------------------


def _temp_zip_files() -> set[Path]:
    """Archivos que matchean el patron de `build_zip_archive` (services/output.py) en
    el directorio temporal del sistema, en este instante. Comparar el resultado antes
    y despues de una descarga detecta un temporal huerfano sin necesitar mockear
    `tempfile` ni asumir una ruta fija."""
    pattern = f"{output_service._TEMP_ZIP_PREFIX}*{output_service._TEMP_ZIP_SUFFIX}"
    return set(Path(tempfile.gettempdir()).glob(pattern))


def test_download_does_not_leave_a_temp_zip_behind(
    client: TestClient, converted_export_id: str
) -> None:
    before = _temp_zip_files()

    response = client.get(f"/api/v1/exports/{converted_export_id}/download")

    assert response.status_code == 200
    after = _temp_zip_files()
    assert after == before, f"quedaron temporales huerfanos: {after - before}"


@pytest.mark.parametrize(
    ("range_header", "expected_status"),
    [
        ("bytes=abc", 400),  # Range malformado -> MalformedRangeHeader
        ("bytes=99999999999-", 416),  # fuera de tamano -> RangeNotSatisfiable
        ("bytes=0-99", 206),  # control: Range valido, SI pasa por `background`
    ],
)
def test_a_range_request_does_not_leave_a_temp_zip_behind(
    client: TestClient, converted_export_id: str, range_header: str, expected_status: int
) -> None:
    """Quinta ronda de revision de M3: `FileResponse.__call__` no corre `background`
    para los dos `return` tempranos de un header `Range` invalido/no-satisfacible.
    `TempZipResponse` (services/output.py) cubre esto con un `finally` propio."""
    before = _temp_zip_files()

    response = client.get(
        f"/api/v1/exports/{converted_export_id}/download",
        headers={"Range": range_header},
    )

    assert response.status_code == expected_status
    after = _temp_zip_files()
    assert after == before, f"quedaron temporales huerfanos: {after - before}"


def test_two_downloads_in_a_row_do_not_clobber_each_other(
    client: TestClient, converted_export_id: str
) -> None:
    """Cada descarga arma su PROPIO temporal (`tempfile.mkstemp`, nombre unico por
    construccion): dos descargas seguidas sobre el mismo export no deberian pisarse
    entre si, y ninguna de las dos deberia dejar basura despues."""
    before = _temp_zip_files()

    first = client.get(f"/api/v1/exports/{converted_export_id}/download")
    second = client.get(f"/api/v1/exports/{converted_export_id}/download")

    for response in (first, second):
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            assert zf.testzip() is None
    assert first.content == second.content

    assert _temp_zip_files() == before


def test_a_failure_while_building_the_zip_cleans_up_the_partial_temp_file(
    client: TestClient, converted_export_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`build_zip_archive` debe borrar el temporal PARCIAL si algo falla a mitad de
    camino, nunca dejar basura en el directorio temporal del sistema. El fallo se
    propaga (se vuelve 500 problem+json via el exception handler generico de
    main.py, ver test_error_handling.py), no se traga en silencio.

    Usa un `TestClient` propio con `raise_server_exceptions=False` (en vez del
    fixture `client` compartido): por default `TestClient` vuelve a lanzar
    cualquier excepcion no manejada en el test en vez de dejar que el handler
    generico de `main.py` la convierta en la respuesta 500 real (mismo criterio que
    `test_error_handling.py::client`). El export ya convertido se registro con el
    `client` normal; el `ExportStore`/`JobStore` son singletons de modulo, asi que
    un segundo `TestClient` sobre la MISMA `app` los ve igual."""
    real_iter = output_service._iter_files_sorted

    def _boom(root: Path) -> list[tuple[Path, str]]:
        real_iter(root)  # confirma que de verdad se llego a listar el arbol
        raise RuntimeError("disco lleno (simulado)")

    monkeypatch.setattr(output_service, "_iter_files_sorted", _boom)
    before = _temp_zip_files()

    with TestClient(app, raise_server_exceptions=False) as lenient_client:
        response = lenient_client.get(f"/api/v1/exports/{converted_export_id}/download")

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert _temp_zip_files() == before


def _output_dir_of(client: TestClient, export_id: str) -> Path:
    """Helper de test: reconstruye la ruta de `_output/` preguntandole a la propia
    API por el arbol y confiando en `services.exports` solo para el prefijo (no hay
    endpoint publico que devuelva la ruta absoluta, a proposito: no es de incumbencia
    del cliente HTTP)."""
    from claude_export_md_api.services import exports as exports_service

    return exports_service.output_directory(export_id)
