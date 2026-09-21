"""`GET /exports/{id}/output/tree`, `GET /exports/{id}/output/file` y
`GET /exports/{id}/download` (spec 06, cuarta ronda de fixes de M3).

Los tres leen EXCLUSIVAMENTE de `exports_service.output_directory(export_id)` (la
carpeta que `POST /convert` ya escribio, `services/jobs.py`). Ninguno sabe de
parseo ni de core mas alla de eso.

Decisiones de este modulo:

* **"Export sin convertir todavia" -> 404**, con un `detail` que lo distingue del 404
  de `export_id` inexistente (`require_output_dir`). Se eligio 404 y no 409 porque,
  desde el punto de vista del cliente, `_output/` es un recurso mas bajo `exports/{id}`
  (como `/inventory`) y "todavia no existe" es exactamente lo que 404 comunica; 409
  se reserva para un conflicto de ESTADO sobre un recurso que si existe (no es el caso:
  antes de `convert` no hay ningun arbol de salida que mostrar, punto).
* **CA-4 (path traversal) se resuelve en dos capas** en `_validate_relative_path` +
  `resolve_output_file`: primero se rechazan, sobre el STRING crudo y sin tocar el
  filesystem, cualquier ruta absoluta y cualquier componente `.`/`..`/vacio (usando
  `PureWindowsPath`, que entiende `/` y `\\` como separador sin importar en que SO
  corre la API - asi `..\\..\\windows\\win.ini` se rechaza igual en Windows y en Linux);
  despues, ya con la ruta candidata construida, `resolve()` + `relative_to()` vuelven
  a confirmar que el resultado sigue siendo descendiente de `_output/` (defensa en
  profundidad, por si algun symlink dentro del arbol intentara escapar). Mismo
  criterio en espiritu que `services/exports.py::_validate_upload_filename`: validar
  ANTES de tocar disco, nunca "limpiar" una ruta sospechosa para intentar usarla igual.
* **El zip de `/download` YA NO se arma con streaming manual** (cuarta ronda de fixes
  de M3: tres rechazos seguidos del reviewer sobre el mismo mecanismo de
  hilo-productor + `queue.Queue` acotada - ver STATUS.md, ronda 4). Ese diseño
  resolvia el streaming "real" a costa de una maquina de hilo+cola+cancelacion que
  seguia rompiendose: el ultimo bug encontrado era de fondo (un abort duro del cliente
  podia dejar el hilo productor bloqueado para siempre en `queue.put()`, sin que nada
  externo lo notara, agotando el pool compartido de `asyncio.to_thread` con las
  conversiones) y ademas media ~42 KB/s de throughput real por ir al pool de hilos en
  cada chunk. La decision (del usuario, explicita, tras el historial de 3 rechazos) es
  SIMPLIFICAR: `build_zip_archive` arma el zip COMPLETO en un archivo temporal dentro
  de un UNICO `asyncio.to_thread` (ver `routers/output.py`), y el router lo sirve con
  `TempZipResponse` (mas abajo), que borra el temporal en un `finally` propio - no con
  `BackgroundTask` (quinta ronda: `FileResponse.__call__` no lo corre si el header
  `Range` es invalido o no satisfacible). Se pierde el
  streaming incremental (memoria/tiempo constante mientras se arma el zip), pero
  desaparece TODA la maquina de cancelacion: no hay hilo productor que pueda quedar
  colgado, no hay cola, no hay `cancel_event`, no hay timeout de inactividad. El
  archivo temporal SI es seekable (a diferencia del stream no-seekable de antes), asi
  que `zipfile.ZipFile` escribe headers normales sin necesitar "data descriptors".
"""

from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Literal

from fastapi.responses import FileResponse
from starlette.types import Receive, Scope, Send

from claude_export_md_api.errors import ProblemError
from claude_export_md_api.services import exports as exports_service

logger = logging.getLogger(__name__)

#: Las dos formas que puede tomar una fila de `list_tree`.
TreeEntryKind = Literal["file", "dir"]

#: Prefijo/sufijo del archivo temporal de `build_zip_archive`: permite reconocerlo en
#: el directorio temporal del sistema (tests, diagnostico) sin depender de un uuid.
_TEMP_ZIP_PREFIX = "cem-download-"
_TEMP_ZIP_SUFFIX = ".zip"


@dataclass(frozen=True, slots=True)
class TreeEntry:
    """Una fila de `GET /output/tree`: ruta relativa POSIX bajo `_output/`, marcada
    como archivo o carpeta. Lista PLANA (no arbol anidado): mas facil de consumir del
    lado del cliente (Angular puede agrupar el mismo por el separador `/` si quiere
    mostrarlo como arbol) y no hace falta inventar un schema recursivo."""

    path: str
    kind: TreeEntryKind
    size: int | None


def require_output_dir(export_id: str) -> Path:
    """`export_directory` (services/exports.py) ya lanza 404 si `export_id` no existe.

    Si el export existe pero `_output/` todavia no, es que nunca se corrio
    `POST /convert` (o el job no termino): se responde 404 tambien, pero con un
    `detail` que lo distingue del 404 de export inexistente (ver docstring del
    modulo). Llamar a esto ANTES de construir cualquier `StreamingResponse`/generador:
    un `ProblemError` lanzado desde dentro de un generador ya en curso llega tarde,
    con la respuesta ya empezada (mismo criterio que `services/jobs.py::stream_job_events`).
    """
    directory = exports_service.output_directory(export_id)
    if not directory.is_dir():
        raise ProblemError(
            status=404,
            title="Export no convertido todavia",
            detail=(
                f"El export '{export_id}' no tiene un arbol de salida todavia: "
                "corre POST /exports/{id}/convert y espera a que el job llegue a "
                "'done' (GET /jobs/{id}) antes de pedir /output o /download."
            ),
        )
    return directory


def _iter_tree(root: Path) -> Iterator[TreeEntry]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()  # recorrido deterministico (CLAUDE.md 1.4)
        current = Path(dirpath)
        if current != root:
            yield TreeEntry(path=current.relative_to(root).as_posix(), kind="dir", size=None)
        for filename in sorted(filenames):
            file_path = current / filename
            yield TreeEntry(
                path=file_path.relative_to(root).as_posix(),
                kind="file",
                size=file_path.stat().st_size,
            )


def list_tree(export_id: str) -> list[TreeEntry]:
    """`GET /output/tree`: todas las rutas (archivos y carpetas) bajo `_output/`,
    ordenadas por ruta para que la salida sea deterministica entre corridas."""
    root = require_output_dir(export_id)
    return sorted(_iter_tree(root), key=lambda entry: entry.path)


def _validate_relative_path(raw: str | None) -> tuple[str, ...]:
    """Primera capa de CA-4: rechaza sobre el STRING crudo, sin tocar el filesystem.

    `PureWindowsPath` entiende `/` y `\\` como separador de ruta sin importar el SO
    donde corre la API (a diferencia de `PurePosixPath`, que trataria `\\` como un
    caracter literal del nombre) - asi ambas formas de escape del CA-4 se detectan
    igual en Windows y en Linux/CI.
    """
    if raw is None or raw.strip() == "":
        raise ProblemError(
            status=400,
            title="Ruta invalida",
            detail="El parametro 'path' es obligatorio.",
        )
    # Bloqueante 4: rechazar CUALQUIER caracter de control ASCII (incluido el byte
    # NUL) sobre el STRING crudo, ANTES de construir ningun `Path`. Sin esto,
    # `candidate.resolve()` mas abajo lanza `ValueError: embedded null character in
    # path` para un `path=..%00..` - una excepcion que NINGUN exception handler de
    # main.py atrapaba, resultando en un 500 crudo de Starlette
    # (`content-type: text/plain`) en vez de `application/problem+json` como
    # CUALQUIER otro error de esta API. Mismo criterio que el resto de esta funcion:
    # validar antes de tocar el filesystem, nunca "limpiar" un string sospechoso.
    if any(ord(ch) < 0x20 for ch in raw):
        raise ProblemError(
            status=400,
            title="Ruta invalida",
            detail=f"{raw!r} contiene un caracter de control invalido.",
        )
    candidate = PureWindowsPath(raw)
    if candidate.drive or candidate.root:
        raise ProblemError(
            status=400,
            title="Ruta invalida",
            detail=f"'{raw}' no puede ser una ruta absoluta.",
        )
    parts = candidate.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ProblemError(
            status=400,
            title="Ruta invalida",
            detail=f"'{raw}' no es una ruta relativa valida dentro del export.",
        )
    return parts


def resolve_output_file(export_id: str, raw_path: str | None) -> Path:
    """`GET /output/file?path=...`: resuelve `raw_path` DENTRO de `_output/`.

    CA-4: `raw_path` con `..`, ruta absoluta, o cualquier forma de escaparse de
    `_output/` -> 400 problem+json, ANTES de tocar el filesystem (`_validate_relative_path`).
    Ya con la ruta candidata construida, se vuelve a confirmar que sigue siendo
    descendiente de `_output/` con `resolve()` + `relative_to()` (defensa en
    profundidad: cubre el caso, no probado por los tests pero real en produccion, de
    un symlink dentro del arbol que apuntara afuera).

    `raw_path` sintacticamente valido pero que no existe en el arbol -> 404.
    """
    root = require_output_dir(export_id)
    parts = _validate_relative_path(raw_path)

    candidate = root.joinpath(*parts)
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ProblemError(
            status=400,
            title="Ruta invalida",
            detail=f"'{raw_path}' se escapa del arbol de salida del export.",
        ) from exc

    if not resolved_candidate.is_file():
        raise ProblemError(
            status=404,
            title="Archivo no encontrado",
            detail=f"'{raw_path}' no existe dentro del arbol de salida del export.",
        )
    return resolved_candidate


def guess_media_type(path: Path) -> str:
    """`.md` no esta en la tabla estandar de `mimetypes` en todas las plataformas;
    el resto (el caso comun de `artifacts/`: `.json`, `.py`, `.png`...) lo infiere
    `mimetypes` solo."""
    media_type, _ = mimetypes.guess_type(path.name)
    if media_type is not None:
        return media_type
    if path.suffix == ".md":
        return "text/markdown; charset=utf-8"
    return "application/octet-stream"


def _iter_files_sorted(root: Path) -> list[tuple[Path, str]]:
    """`(ruta en disco, arcname posix)` de cada ARCHIVO bajo `root`, en orden
    deterministico (mismo criterio que `list_tree`)."""
    files: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        current = Path(dirpath)
        for filename in sorted(filenames):
            file_path = current / filename
            files.append((file_path, file_path.relative_to(root).as_posix()))
    files.sort(key=lambda item: item[1])
    return files


def build_zip_archive(output_dir: Path) -> Path:
    """Cuerpo (sincrono, pensado para correr dentro de un UNICO `asyncio.to_thread`)
    de `GET /exports/{id}/download`: arma el zip COMPLETO del arbol de `output_dir` en
    un archivo temporal propio y devuelve su ruta, ya cerrado y listo para servir.

    Reemplaza la maquina de hilo-productor + `queue.Queue` acotada de las rondas
    anteriores (ver docstring del modulo): un archivo temporal SI es seekable, asi que
    `zipfile.ZipFile` puede escribir sobre el con el modo normal (headers reescritos al
    cerrar, sin "data descriptors") - mas simple y sin ningun mecanismo propio de
    cancelacion.

    `tempfile.mkstemp` (no `NamedTemporaryFile`) porque el archivo tiene que sobrevivir
    a esta funcion (el router lo sirve DESPUES, con `FileResponse`): se abre un
    descriptor propio, se cierra de inmediato (`zipfile.ZipFile` lo vuelve a abrir por
    ruta) y el archivo en si queda en disco hasta que `remove_temp_zip` lo borre.

    Si algo falla a mitad de camino (un archivo que desaparecio entre `list_tree` y
    esta llamada, disco lleno, lo que sea), el temporal PARCIAL se borra antes de
    relanzar - nunca se deja basura a medio escribir en el directorio temporal del
    sistema.
    """
    fd, raw_path = tempfile.mkstemp(prefix=_TEMP_ZIP_PREFIX, suffix=_TEMP_ZIP_SUFFIX)
    os.close(fd)
    zip_path = Path(raw_path)
    try:
        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path, arcname in _iter_files_sorted(output_dir):
                zf.write(file_path, arcname=arcname)
    except BaseException:
        zip_path.unlink(missing_ok=True)
        raise
    return zip_path


def remove_temp_zip(zip_path: Path) -> None:
    """Borra el temporal de `build_zip_archive`. `missing_ok=True` porque nunca deberia
    fallar el borrado del propio temporal, pero tampoco hay motivo para que una llamada
    duplicada (o una corrida de tests) tire una excepcion sobre algo que ya no esta."""
    zip_path.unlink(missing_ok=True)


class TempZipResponse(FileResponse):
    """`FileResponse` de un archivo temporal PROPIO (nunca del usuario): garantiza el
    borrado envolviendo `__call__` en un `try/finally`, en vez de confiar en el
    `background=` de `FileResponse`.

    Cuarta revision de M3: `FileResponse.__call__` NO llega siempre a `await
    self.background()` - starlette/responses.py hace `return` temprano para un header
    `Range` malformado (400) o no satisfacible (416), salteando la linea del
    `background` (verificado leyendo starlette 1.6.0: `except MalformedRangeHeader` y
    `except RangeNotSatisfiable` devuelven una `PlainTextResponse` propia y cortan antes
    de esa linea). Como cada `/download` arma un zip nuevo, un `Range` calculado contra
    una descarga anterior puede caer fuera de tamano -> 416 -> el temporal quedaba
    huerfano para siempre. El `finally` de acá cubre los dos casos (el camino normal Y
    los dos `return` tempranos de Range) sin depender de que hint interno de Starlette.

    El borrado nunca debe ocultar una excepcion genuina del envio (revision de M3,
    ronda 5): si `unlink` falla (otro proceso con el archivo abierto - antivirus,
    indexador, backup; plausible en la v2 de Windows con PyInstaller), se loguea y se
    sigue, en vez de que el `OSError` del borrado tape lo que de verdad paso."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                remove_temp_zip(Path(self.path))
            except OSError:
                logger.warning("No se pudo borrar el temporal %s", self.path, exc_info=True)


__all__ = [
    "TempZipResponse",
    "TreeEntry",
    "build_zip_archive",
    "guess_media_type",
    "list_tree",
    "remove_temp_zip",
    "require_output_dir",
    "resolve_output_file",
]
