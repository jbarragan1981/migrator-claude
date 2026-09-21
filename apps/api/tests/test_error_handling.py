"""`main.py::_handle_unexpected_exception` (spec 06, bloqueante 4 de la revision de M3).

Red de seguridad: CUALQUIER excepcion no anticipada en CUALQUIER endpoint debe
traducirse a `500 application/problem+json`, nunca al 500 crudo de
Starlette/FastAPI (`content-type: text/plain`) - eso rompia el contrato de que
todos los errores de la API tienen forma RFC 7807 (ver services/output.py, el
byte NUL de `path=` es el caso puntual que lo disparo, pero el handler generico
cubre cualquier excepcion futura, no solo esa).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from claude_export_md_api.main import app
from claude_export_md_api.services import exports as exports_service

PROBLEM_JSON = "application/problem+json"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_an_arbitrary_unhandled_exception_becomes_a_500_problem_json_not_a_raw_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Excepcion generica, sin ninguna relacion con path traversal ni con NUL bytes,
    forzada en un endpoint existente (`GET /exports/{id}/inventory`) via monkeypatch:
    el handler generico de main.py debe atraparla iguial y devolver problem+json, en
    vez de dejar pasar el 500 plano por defecto de Starlette."""

    def _boom(export_id: str) -> None:
        raise RuntimeError("fallo interno arbitrario, no anticipado por ningun handler especifico")

    monkeypatch.setattr(exports_service, "inventory_for", _boom)

    response = client.get("/api/v1/exports/does-not-matter/inventory")

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["status"] == 500
    assert body["title"] == "Error interno"
    # El detalle NUNCA filtra el mensaje real de la excepcion ni el stack trace.
    assert "fallo interno arbitrario" not in body.get("detail", "")
    assert "RuntimeError" not in body.get("detail", "")
