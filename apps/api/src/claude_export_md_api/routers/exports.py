"""`POST /exports`, `GET /exports/{id}/inventory` y `DELETE /exports/{id}` (spec 06).

Router fino: solo decide que "forma" trae el request y llama a `services/exports.py`
(o a `services/lifecycle.py` para el DELETE). Ningun endpoint hace llamadas de red
salientes ni usa el `export_url` del manifiesto (CLAUDE.md 5).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response
from pydantic import ValidationError

from claude_export_md import Inventory
from claude_export_md_api.errors import ProblemError
from claude_export_md_api.schemas.exports import ExportCreateResponse, LocalExportRequest
from claude_export_md_api.schemas.problem import problem_responses
from claude_export_md_api.services import exports as exports_service
from claude_export_md_api.services import lifecycle as lifecycle_service

router = APIRouter(tags=["exports"])

#: `create_export` lee el body "a mano" (ver docstring), asi que FastAPI no puede
#: inferir el requestBody de un parametro tipado - sin esto el openapi.json documenta
#: el endpoint sin ningun body, y el cliente generado en M4 no podria mandar ni la
#: ruta local ni los archivos. Los dos modos son mutuamente excluyentes por
#: content-type (multipart vs JSON), de ahi el `oneOf`.
_CREATE_EXPORT_REQUEST_BODY = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "array",
                        "items": {"type": "string", "format": "binary"},
                        "description": "Uno o mas zips y/o el member-manifest-*.json.",
                    }
                },
                "required": ["file"],
            }
        },
        "application/json": {"schema": LocalExportRequest.model_json_schema()},
    },
}


@router.post(
    "/exports",
    status_code=201,
    response_model=ExportCreateResponse,
    responses=problem_responses(400, 403, 413),
    openapi_extra={"requestBody": _CREATE_EXPORT_REQUEST_BODY},
)
async def create_export(request: Request) -> ExportCreateResponse:
    """Multipart -> subida; cualquier otro content-type -> se interpreta como `{"path"}`.

    Los dos modos comparten la misma ruta HTTP (spec 06) pero necesitan cuerpos de
    forma distinta, asi que el request se lee "a mano" en vez de declarar dos
    parametros (`UploadFile` y un modelo pydantic) que FastAPI no puede combinar en
    un unico endpoint.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        export_id = await exports_service.register_upload(request)
        return ExportCreateResponse(export_id=export_id)

    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise ProblemError(
            status=400,
            title="Cuerpo invalido",
            detail="Se esperaba JSON con {'path': ...} o una subida multipart.",
        ) from exc

    try:
        body = LocalExportRequest.model_validate(payload)
    except ValidationError as exc:
        raise ProblemError(status=400, title="Cuerpo invalido", detail=str(exc)) from exc

    export_id = exports_service.register_local_path(body.path)
    return ExportCreateResponse(export_id=export_id)


@router.get(
    "/exports/{export_id}/inventory",
    response_model=Inventory,
    responses=problem_responses(404, 422),
)
async def get_export_inventory(export_id: str) -> Inventory:
    return exports_service.inventory_for(export_id)


@router.delete(
    "/exports/{export_id}",
    status_code=204,
    responses=problem_responses(404, 409),
)
async def delete_export(export_id: str) -> Response:
    """Ver decisiones en `services/lifecycle.py::delete_export` (id inexistente -> 404,
    modo local solo borra `_output/`, modo subida borra el directorio de trabajo entero)."""
    lifecycle_service.delete_export(export_id)
    return Response(status_code=204)
