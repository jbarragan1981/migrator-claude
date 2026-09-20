"""FastAPI app: registra el router de `/api/v1`, el exception handler RFC 7807 y `/health`."""

from __future__ import annotations

import http
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from claude_export_md_api.errors import ProblemError
from claude_export_md_api.routers.exports import router as exports_router
from claude_export_md_api.routers.jobs import router as jobs_router
from claude_export_md_api.routers.output import router as output_router

logger = logging.getLogger(__name__)

app = FastAPI(title="claude-export-md API", version="0.1.0")
app.include_router(exports_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(output_router, prefix="/api/v1")


def _problem_response(
    status: int, title: str, detail: str | None, type_: str = "about:blank"
) -> JSONResponse:
    body: dict[str, object] = {"type": type_, "title": title, "status": status}
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(status_code=status, content=body, media_type="application/problem+json")


@app.exception_handler(ProblemError)
async def _handle_problem_error(request: Request, exc: ProblemError) -> JSONResponse:
    return _problem_response(exc.status, exc.title, exc.detail, exc.type)


@app.exception_handler(StarletteHTTPException)
async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    try:
        title = http.HTTPStatus(exc.status_code).phrase
    except ValueError:  # pragma: no cover - codigo HTTP no estandar
        title = "Error"
    return _problem_response(exc.status_code, title, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _problem_response(422, "Solicitud invalida", str(exc.errors()))


@app.exception_handler(Exception)
async def _handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
    """Red de seguridad (bloqueante 4 de la revision de M3): cualquier excepcion no
    anticipada en cualquier endpoint (de hoy o de una ronda futura) NUNCA debe llegar
    al cliente como el 500 crudo de Starlette (`content-type: text/plain`) - rompe el
    contrato de que TODOS los errores de esta API son `application/problem+json`. El
    `detail` es deliberadamente generico: no se filtra el mensaje de la excepcion ni
    el stack trace interno al cliente; el detalle real queda solo en el log del
    servidor.
    """
    logger.exception(
        "Excepcion no manejada en %s %s", request.method, request.url.path, exc_info=exc
    )
    return _problem_response(500, "Error interno", "Ocurrio un error interno inesperado.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
