"""Request/response de `POST /exports/{id}/convert`, `GET /jobs/{id}` y los datos que
viajan por el SSE de `GET /jobs/{id}/events` (spec 06).
"""

from __future__ import annotations

from pydantic import BaseModel

from claude_export_md_api.services.jobs import JobStatus


class ConvertRequest(BaseModel):
    """Body opcional de `POST /exports/{id}/convert`.

    `only` esta documentado en el spec 06 pero `usecases.convert.convert()` de core
    todavia no acepta filtrar categorias (mismo pendiente que `--only` del CLI, ver
    docs/specs/05-cli.md y STATUS.md): se acepta el campo para no romper el contrato,
    pero no tiene efecto todavia (`services/jobs.py::start_conversion` deja un warning
    en el log si se manda).
    """

    only: list[str] | None = None
    templates: str | None = None


class JobCreateResponse(BaseModel):
    """`202` de `POST /exports/{id}/convert`."""

    job_id: str


class ProgressEventSchema(BaseModel):
    category: str
    done: int


class JobStatusResponse(BaseModel):
    """`GET /jobs/{id}` (spec 06): `{status, progress, counts, errors}` mas el motivo
    de un `failed` (incluido `"timeout"`, CA-6) y las advertencias, que no rompen el
    contrato del spec (son un campo adicional, no uno de los pedidos)."""

    status: JobStatus
    progress: list[ProgressEventSchema]
    counts: dict[str, int] | None = None
    errors: int | None = None
    warnings: int | None = None
    reason: str | None = None


__all__ = [
    "ConvertRequest",
    "JobCreateResponse",
    "JobStatusResponse",
    "ProgressEventSchema",
]
