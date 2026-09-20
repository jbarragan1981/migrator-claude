"""`GET /exports/{id}/output/tree`, `GET /exports/{id}/output/file` y
`GET /exports/{id}/download` (spec 06).

Router fino: resolucion de rutas (incluida la defensa anti path-traversal de CA-4) y
el armado del zip viven enteros en `services/output.py`.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from claude_export_md_api.schemas.output import OutputTreeEntry, OutputTreeResponse
from claude_export_md_api.services import output as output_service
from claude_export_md_api.services.output import TempZipResponse

router = APIRouter(tags=["output"])


@router.get("/exports/{export_id}/output/tree", response_model=OutputTreeResponse)
async def get_output_tree(export_id: str) -> OutputTreeResponse:
    entries = output_service.list_tree(export_id)
    return OutputTreeResponse(
        entries=[OutputTreeEntry(path=e.path, kind=e.kind, size=e.size) for e in entries]
    )


@router.get("/exports/{export_id}/output/file")
async def get_output_file(export_id: str, path: str = Query(...)) -> FileResponse:
    resolved = output_service.resolve_output_file(export_id, path)
    media_type = output_service.guess_media_type(resolved)
    return FileResponse(resolved, media_type=media_type, filename=resolved.name)


@router.get("/exports/{export_id}/download")
async def download_export(export_id: str) -> FileResponse:
    # Se resuelve ANTES de armar el zip: un 404 lanzado DESPUES de haber pasado minutos
    # comprimiendo un arbol grande seria un desperdicio, y ademas rompe el mismo
    # criterio que el resto del modulo (ver services/output.py::require_output_dir).
    root = output_service.require_output_dir(export_id)
    # Diseno simple (cuarta ronda de fixes de M3, ver docstring de services/output.py):
    # se arma el zip COMPLETO en un archivo temporal dentro de un UNICO
    # `asyncio.to_thread` (nunca ir al pool de hilos chunk a chunk, como hacia el
    # mecanismo de streaming manual que este reemplaza). Se sirve con `TempZipResponse`
    # (no `FileResponse` + `background=`): `FileResponse.__call__` no llega a correr el
    # `background` cuando un header `Range` es invalido o no satisfacible (400/416,
    # quinta ronda de revision de M3) - `TempZipResponse` borra el temporal en un
    # `finally` propio, que cubre esos dos casos ademas del camino normal.
    zip_path = await asyncio.to_thread(output_service.build_zip_archive, root)
    filename = f"claude-export-md-{export_id}.zip"
    return TempZipResponse(zip_path, media_type="application/zip", filename=filename)
