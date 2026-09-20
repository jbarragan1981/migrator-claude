"""Forma de error comun a toda la API: RFC 7807 (`application/problem+json`).

Solo describe la forma; quien la instancia es el exception handler central de
`main.py`, nunca un router (CLAUDE.md 7, spec 06 seccion "Errores").
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Problem(BaseModel):
    """https://www.rfc-editor.org/rfc/rfc7807 - un problem detail minimo."""

    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
