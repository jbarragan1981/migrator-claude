"""Respuesta de `GET /api/v1/exports/{id}/output/tree` (spec 06).

`/output/file` y `/download` no tienen schema propio: devuelven bytes crudos
(`FileResponse`/`StreamingResponse`), no JSON.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class OutputTreeEntry(BaseModel):
    """Una fila del arbol de salida: ruta relativa POSIX bajo `_output/`.

    Se devuelve como LISTA PLANA (`OutputTreeResponse.entries`), no como arbol
    anidado: cada entrada ya trae su ruta completa (`"conversations/2026/09"`,
    `"conversations/2026/09/2026-09-01_titulo_ab12cd34.md"`...), asi que el cliente
    puede reconstruir la jerarquia partiendo por `/` si la quiere mostrar como arbol,
    sin que el servidor tenga que modelar un schema recursivo para eso.
    """

    path: str
    kind: Literal["file", "dir"]
    #: Tamano en bytes; `None` para `kind == "dir"`.
    size: int | None = None


class OutputTreeResponse(BaseModel):
    entries: list[OutputTreeEntry]


__all__ = ["OutputTreeEntry", "OutputTreeResponse"]
