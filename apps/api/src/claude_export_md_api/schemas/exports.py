"""Request/response de `POST /api/v1/exports` y `GET /api/v1/exports/{id}/inventory`.

El inventario en si NO se reenvuelve: `routers/exports.py` devuelve directamente el
`claude_export_md.Inventory` de core (ya es un `BaseModel` serializable), para no
duplicar esa forma (ver encargo de la tarea).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExportCreateResponse(BaseModel):
    """`201` de `POST /exports`, para los dos modos (local y multipart)."""

    export_id: str


class LocalExportRequest(BaseModel):
    """Cuerpo JSON aceptado en modo local: `{"path": "..."}` (spec 06 CA-9).

    El `export_url` de un manifiesto NUNCA se acepta aqui (CLAUDE.md 5): este modelo
    solo conoce `path`, cualquier otra clave del JSON de entrada se ignora.
    """

    path: str = Field(min_length=1)
