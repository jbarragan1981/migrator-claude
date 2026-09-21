"""Registro de exports (modo local o subida) y su inventario (spec 06, primera ronda de M3).

`ExportStore` es deliberadamente simple: un dict `export_id -> ExportRecord` protegido
por un lock, en memoria. El `JobStore` de verdad (para `/convert`, `/jobs`) es la
proxima ronda; esto solo necesita recordar que carpeta corresponde a que id.

Reglas de CLAUDE.md 5/9 que este modulo respeta:
- el `export_url` de un manifiesto nunca se usa (no hay llamadas de red salientes);
- el directorio de trabajo de una subida vive fuera del repo (`CEM_WORK_DIR`, por
  defecto el temp del sistema) y se limpia si la subida se rechaza a mitad de camino;
- una ruta local (modo `{"path"}`) es del usuario: se lee, nunca se mueve ni se borra.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from starlette.datastructures import UploadFile

from claude_export_md import ClaudeExportMdError, Inventory, build_inventory, create_source
from claude_export_md_api.errors import ProblemError

#: Gatea el modo local (spec 06 CA-9). Apagado por defecto: en docker compose nunca
#: se debe poder leer el filesystem del contenedor del API a pedido del cliente.
ALLOW_LOCAL_PATHS_ENV = "CEM_ALLOW_LOCAL_PATHS"
#: Limite de subida en megabytes (spec 06 CA-5).
MAX_UPLOAD_MB_ENV = "CEM_MAX_UPLOAD_MB"
#: Carpeta base para los directorios de trabajo de las subidas. NUNCA dentro del repo.
WORK_DIR_ENV = "CEM_WORK_DIR"

DEFAULT_MAX_UPLOAD_MB = 2048

#: Tamano de lectura/escritura por chunk al volcar una subida a disco: el archivo
#: nunca se materializa completo en memoria, se compara contra el limite a medida
#: que llega (ver `register_upload`).
_UPLOAD_CHUNK_BYTES = 1024 * 1024


def local_paths_allowed() -> bool:
    return os.environ.get(ALLOW_LOCAL_PATHS_ENV, "").strip().lower() == "true"


def max_upload_bytes() -> int:
    raw = os.environ.get(MAX_UPLOAD_MB_ENV, "").strip()
    try:
        megabytes = int(raw) if raw else DEFAULT_MAX_UPLOAD_MB
    except ValueError:
        megabytes = DEFAULT_MAX_UPLOAD_MB
    return megabytes * 1024 * 1024


def _work_dir_base() -> Path:
    configured = os.environ.get(WORK_DIR_ENV, "").strip()
    base = Path(configured) if configured else Path(tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    return base


def _new_export_dir() -> tuple[str, Path]:
    export_id = str(uuid.uuid4())
    directory = _work_dir_base() / f"claude-export-md-{export_id}"
    directory.mkdir(parents=True, exist_ok=False)
    return export_id, directory


@dataclass(frozen=True)
class ExportRecord:
    export_id: str
    path: Path
    #: True: directorio temporal propio (subida), lo creamos y lo limpiamos nosotros.
    #: False: ruta del usuario (modo local), solo se lee, nunca se toca.
    owned: bool


class ExportStore:
    """`export_id -> ExportRecord`, en memoria (el JobStore real es otra ronda)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, ExportRecord] = {}

    def add(self, record: ExportRecord) -> None:
        with self._lock:
            self._records[record.export_id] = record

    def get(self, export_id: str) -> ExportRecord | None:
        with self._lock:
            return self._records.get(export_id)

    def remove(self, export_id: str) -> ExportRecord | None:
        """Olvida el registro (usado por `DELETE /exports/{id}`, services/lifecycle.py).

        Solo quita la entrada del store; NO toca el filesystem. Devuelve el registro
        borrado (o `None` si `export_id` no existia) para que quien llama sepa si
        habia algo que borrar.
        """
        with self._lock:
            return self._records.pop(export_id, None)


_store = ExportStore()


def get_store() -> ExportStore:
    """Unico punto de acceso al store (facilita reemplazarlo en tests si hiciera falta)."""
    return _store


def register_local_path(raw_path: str) -> str:
    """Modo local: registra `raw_path` si `CEM_ALLOW_LOCAL_PATHS=true` (CA-9)."""
    if not local_paths_allowed():
        raise ProblemError(
            status=403,
            title="Modo local desactivado",
            detail=(
                f"{ALLOW_LOCAL_PATHS_ENV} no esta en 'true': esta instancia no acepta "
                "rutas del sistema de archivos del servidor (spec 06 CA-9)."
            ),
        )
    path = Path(raw_path)
    if not path.exists():
        raise ProblemError(status=400, title="Ruta invalida", detail=f"'{raw_path}' no existe.")
    if not os.access(path, os.R_OK):
        raise ProblemError(
            status=400, title="Ruta invalida", detail=f"'{raw_path}' no se puede leer."
        )

    export_id = str(uuid.uuid4())
    get_store().add(ExportRecord(export_id=export_id, path=path, owned=False))
    return export_id


def _validate_upload_filename(filename: str | None) -> str:
    """Anti path-traversal (CA-4/CA-5 del espiritu de la tarea): se valida ANTES de escribir.

    Las subidas de esta ronda son siempre archivos sueltos (zips o el manifiesto,
    CLAUDE.md 9); ningun nombre legitimo trae separadores de ruta, asi que se
    rechaza cualquiera que los tenga en vez de intentar "limpiarlos".
    """
    if filename is None or not filename.strip():
        raise ProblemError(
            status=400,
            title="Archivo sin nombre",
            detail="Cada parte subida debe traer un nombre de archivo.",
        )
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise ProblemError(
            status=400,
            title="Nombre de archivo invalido",
            detail=(
                f"'{filename}' no se acepta: los archivos subidos van sueltos, sin "
                "separadores de ruta ni '..'."
            ),
        )
    return filename


async def register_upload(request: Request) -> str:
    """Subida multipart: uno o mas archivos (zips y/o `member-manifest-*.json`, CA-1).

    Limite de tamano (CA-5) en dos capas: (a) si el cliente manda `Content-Length`,
    se rechaza antes de leer un solo byte del cuerpo; (b) de todas formas se cuenta
    en streaming mientras se escribe cada archivo, por si el header falta o miente,
    cortando la escritura apenas se supera el limite en vez de esperar a tener todo
    en disco. Ninguna de las dos rutas junta el archivo completo en un `bytes` de
    Python: se lee y se escribe en chunks de `_UPLOAD_CHUNK_BYTES`.
    """
    limit = max_upload_bytes()

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = None
        if declared is not None and declared > limit:
            raise ProblemError(
                status=413,
                title="Subida demasiado grande",
                detail=(
                    f"El cuerpo declarado ({declared} bytes) supera el limite de "
                    f"{limit} bytes ({MAX_UPLOAD_MB_ENV})."
                ),
            )

    form = await request.form()
    try:
        # `form.multi_items()`, NUNCA `form.values()`: `FormData` es un multidict y
        # `.values()` DEDUPLICA por nombre de campo (se queda solo con la ULTIMA parte
        # de cada nombre repetido). El caso real (README) es subir varias partes con
        # el MISMO `name="file"` - con `.values()` eso perdia archivos en silencio,
        # con un 201 igual (bloqueante 1 de la revision de M3).
        uploads = [
            value
            for _field_name, value in form.multi_items()
            if isinstance(value, UploadFile) and value.filename
        ]
        if not uploads:
            raise ProblemError(
                status=400, title="Subida vacia", detail="No se recibio ningun archivo."
            )

        # Se validan TODOS los nombres antes de escribir el primer byte a disco.
        for upload in uploads:
            _validate_upload_filename(upload.filename)

        export_id, directory = _new_export_dir()
        try:
            total_written = 0
            for upload in uploads:
                assert upload.filename is not None  # ya validado arriba
                destination = directory / upload.filename
                await upload.seek(0)
                with destination.open("wb") as out:
                    while True:
                        chunk = await upload.read(_UPLOAD_CHUNK_BYTES)
                        if not chunk:
                            break
                        total_written += len(chunk)
                        if total_written > limit:
                            raise ProblemError(
                                status=413,
                                title="Subida demasiado grande",
                                detail=(
                                    f"La subida supera el limite de {limit} bytes "
                                    f"({MAX_UPLOAD_MB_ENV})."
                                ),
                            )
                        out.write(chunk)
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise

        get_store().add(ExportRecord(export_id=export_id, path=directory, owned=True))
        return export_id
    finally:
        # Mismo criterio que arriba: `multi_items()` para cerrar TODOS los `UploadFile`
        # que Starlette abrio, no solo los que sobrevivieron una deduplicacion por
        # nombre de campo (con `.values()` los descartados quedaban con su
        # `SpooledTemporaryFile` huerfano, sin cerrar).
        for _field_name, value in form.multi_items():
            if isinstance(value, UploadFile):
                await value.close()


def export_directory(export_id: str) -> Path:
    record = get_store().get(export_id)
    if record is None:
        raise ProblemError(
            status=404,
            title="Export no encontrado",
            detail=f"No existe ningun export con id '{export_id}'.",
        )
    return record.path


#: Subcarpeta del directorio de trabajo del export donde `POST /convert` escribe el
#: arbol Markdown (services/jobs.py). Vive DENTRO del directorio de trabajo del export
#: (local: la ruta del usuario; subida: `<CEM_WORK_DIR>/claude-export-md-<uuid>/`) para
#: que rondas futuras (`/output/tree`, `/output/file`, `/download`) puedan encontrarla
#: a partir del `export_id` sin guardar una ruta aparte en ningun otro lado.
OUTPUT_DIRNAME = "_output"


def output_directory(export_id: str) -> Path:
    """Dónde debe escribir `convert()` el resultado de este export. 404 si no existe."""
    return export_directory(export_id) / OUTPUT_DIRNAME


def inventory_for(export_id: str) -> Inventory:
    """`GET /exports/{id}/inventory`: delega TODO en core (`create_source`/`build_inventory`)."""
    directory = export_directory(export_id)
    try:
        source = create_source(directory)
        return build_inventory(source)
    except ClaudeExportMdError as exc:
        raise ProblemError(
            status=422,
            title="No se pudo inventariar el export",
            detail=str(exc),
        ) from exc
