"""`POST /exports/{id}/convert`, `GET /jobs/{id}` y `GET /jobs/{id}/events` (spec 06).

Router fino: la orquestacion (validar, crear el job, lanzarlo en segundo plano, leer
su estado, armar el SSE) vive entera en `services/jobs.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from claude_export_md_api.schemas.jobs import (
    ConvertRequest,
    JobCreateResponse,
    JobStatusResponse,
    ProgressEventSchema,
)
from claude_export_md_api.services import jobs as jobs_service

router = APIRouter(tags=["jobs"])


@router.post("/exports/{export_id}/convert", status_code=202, response_model=JobCreateResponse)
async def convert_export(export_id: str, body: ConvertRequest | None = None) -> JobCreateResponse:
    payload = body or ConvertRequest()
    job_id = jobs_service.start_conversion(
        export_id, templates=payload.templates, only=payload.only
    )
    return JobCreateResponse(job_id=job_id)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str) -> JobStatusResponse:
    view = jobs_service.job_status(job_id)
    return JobStatusResponse(
        status=view.status,
        progress=[ProgressEventSchema(category=e.category, done=e.done) for e in view.progress],
        counts=view.counts,
        errors=view.error_count,
        warnings=view.warning_count,
        reason=view.reason,
    )


@router.get("/jobs/{job_id}/events")
async def get_job_events(job_id: str, request: Request) -> StreamingResponse:
    # Se chequea ANTES de crear el StreamingResponse: un 404 lanzado desde dentro del
    # generador llega tarde, con la respuesta ya empezada (ver services/jobs.py).
    jobs_service.ensure_job_exists(job_id)
    return StreamingResponse(
        jobs_service.stream_job_events(job_id, request), media_type="text/event-stream"
    )
