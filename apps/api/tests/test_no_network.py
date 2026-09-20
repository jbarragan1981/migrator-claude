"""Ningun endpoint hace llamadas de red salientes (spec 06 CA-8, CLAUDE.md 5).

`TestClient` corre la app en proceso via ASGI, pero el propio arnes de pruebas
(el `BlockingPortal` de anyio) igual necesita crear sockets locales de verdad en
Windows (no hay `socketpair` nativo: se emula conectando dos sockets por loopback).
Por eso esta prueba no bloquea `socket.socket` en si, sino `connect`/`connect_ex`
hacia cualquier destino que NO sea loopback: eso deja pasar la maquinaria interna
del test y sigue detectando cualquier intento real de salir a la red.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from claude_export_md_api.main import app

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class _SocketsForbidden(AssertionError):
    pass


def _host_of(address: Any) -> str | None:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return None


def test_no_endpoint_opens_a_real_socket(
    monkeypatch: pytest.MonkeyPatch, synthetic_export_dir: Path
) -> None:
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _guarded_connect(self: socket.socket, address: Any, *a: object, **kw: object) -> Any:
        host = _host_of(address)
        if host is not None and host not in _LOOPBACK_HOSTS:
            raise _SocketsForbidden(f"conexion saliente bloqueada hacia {address!r}")
        return real_connect(self, address, *a, **kw)

    def _guarded_connect_ex(self: socket.socket, address: Any, *a: object, **kw: object) -> Any:
        host = _host_of(address)
        if host is not None and host not in _LOOPBACK_HOSTS:
            raise _SocketsForbidden(f"conexion saliente bloqueada hacia {address!r}")
        return real_connect_ex(self, address, *a, **kw)

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
    monkeypatch.setenv("CEM_ALLOW_LOCAL_PATHS", "true")

    client = TestClient(app)

    assert client.get("/health").status_code == 200

    created = client.post("/api/v1/exports", json={"path": str(synthetic_export_dir)})
    assert created.status_code == 201
    export_id = created.json()["export_id"]

    inventory = client.get(f"/api/v1/exports/{export_id}/inventory")
    assert inventory.status_code == 200

    upload = client.post(
        "/api/v1/exports",
        files=[("files", ("conversations.json", b"[]", "application/json"))],
    )
    assert upload.status_code == 201
