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


def problem_responses(*statuses: int) -> dict[int | str, dict[str, object]]:
    """`responses=` de un endpoint FastAPI para los codigos de error que puede emitir.

    Sin esto, cada router queda documentado en el `openapi.json` con SOLO el 200 (o
    lo que declare el path decorator), y `Problem` nunca aparece en `components.schemas`
    aunque TODOS los errores de la API salgan con esa forma via el exception handler
    central de `main.py` (deuda tecnica anotada al cerrar M3: rompe CA-7 del spec 06 y
    obliga al cliente Angular de M4 a tipar los errores como `any`)."""
    return {
        status: {"model": Problem, "content": {"application/problem+json": {}}}
        for status in statuses
    }
