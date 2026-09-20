"""`JobStore` en memoria + orquestacion de `POST /convert`, `GET /jobs/{id}` y el SSE
de `GET /jobs/{id}/events` (spec 06, segunda ronda de M3).

Decisiones de este modulo:

* **`convert()` de core es sincrona.** Correrla dentro de una corrutina sin bloquear
  el event loop exige ejecutarla en un thread (`asyncio.to_thread`); el callback de
  progreso que le pasamos entonces se invoca DESDE ESE thread, nunca desde el hilo del
  event loop. Por eso `JobStore`, igual que `ExportStore` (`services/exports.py`), se
  protege con un `threading.Lock` en vez de asumir que todo pasa en un unico hilo.
* **El resultado de un job se escribe DENTRO del directorio de trabajo del export**
  (`exports_service.output_directory`), nunca en otro lado: la proxima ronda
  (`/output/tree`, `/download`) necesita poder encontrarlo solo a partir del
  `export_id`, sin que este modulo tenga que recordar una ruta aparte.
* **Timeout con `asyncio.wait_for`.** Cancela la TAREA de asyncio que espera el
  resultado; el thread de Python que esta corriendo `convert()` no se puede matar a la
  fuerza (limitacion del lenguaje, no de este codigo) y puede seguir escribiendo hasta
  que termine solo, pero nadie vuelve a leer ese resultado: el job ya quedo marcado
  `failed` con motivo `"timeout"` (CA-6) y no se revierte.
* **El generador del SSE nunca bloquea la tarea de fondo.** Poll simple sobre el
  `JobStore` (barato: son listas y dicts en memoria) en vez de coordinar con
  `asyncio.Event`/`Condition` entre el thread de conversion y el loop: evita la
  complejidad de notificar entre hilos sin ganar nada medible a esta escala.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fastapi import Request

from claude_export_md import FilesystemSink, create_source
from claude_export_md.usecases.convert import convert as run_convert
from claude_export_md_api.errors import ProblemError
from claude_export_md_api.services import exports as exports_service

logger = logging.getLogger(__name__)

#: Timeout de un job de conversion, en segundos (spec 06 CA-6).
JOB_TIMEOUT_ENV = "CEM_JOB_TIMEOUT_S"
DEFAULT_JOB_TIMEOUT_S = 300.0

#: Motivo de `failed` cuando el job no termino a tiempo (CA-6). Distinto de cualquier
#: mensaje de excepcion real: el cliente puede confiar en compararlo por igualdad.
TIMEOUT_REASON = "timeout"

#: Intervalo de sondeo del SSE sobre el `JobStore` (ver nota de clase arriba).
_POLL_INTERVAL_S = 0.05

#: Los cuatro estados posibles de un job (spec 06).
JobStatus = Literal["pending", "running", "done", "failed"]

#: Estados en los que un job todavia esta "vivo" (bloquea un nuevo `/convert` sobre
#: el mismo export, observacion 1 de la revision de M3; bloquea `DELETE` sobre el
#: mismo export, observacion 2, en services/lifecycle.py).
_ACTIVE_JOB_STATUSES = ("pending", "running")

#: Bug 2 de la 3ra ronda de revision de M3: `_ACTIVE_JOB_STATUSES` mira solo el
#: ESTADO del job, pero cuando un job vence por `CEM_JOB_TIMEOUT_S` (`TIMEOUT_REASON`)
#: el hilo REAL de `asyncio.to_thread(run_sync)` que corre `convert()` NO se puede
#: matar (limitacion de Python) y sigue escribiendo en `_output/` en segundo plano
#: pese a que el job ya se marco `failed`. "Activo" deja de ser el estado del job y
#: pasa a ser "el worker realmente sigue vivo": ver `_JobState.finished_event` (se
#: activa en el `finally` de `run_sync`, DENTRO del hilo real, nunca cuando el
#: orquestador async decide dejar de esperarlo) y `JobStore._is_active`.


def job_timeout_seconds() -> float:
    raw = os.environ.get(JOB_TIMEOUT_ENV, "").strip()
    try:
        return float(raw) if raw else DEFAULT_JOB_TIMEOUT_S
    except ValueError:
        return DEFAULT_JOB_TIMEOUT_S


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """Un `progress` emitido por `convert()` al terminar (parcial o del todo) una
    categoria (ver `usecases/convert.py::ProgressCallback` de core)."""

    category: str
    done: int


@dataclass(frozen=True, slots=True)
class JobView:
    """Foto de un job en un instante: lo que devuelven `GET /jobs/{id}` y el SSE."""

    job_id: str
    export_id: str
    status: JobStatus
    progress: tuple[ProgressEvent, ...]
    counts: dict[str, int] | None = None
    error_count: int | None = None
    warning_count: int | None = None
    destination: str | None = None
    reason: str | None = None


@dataclass
class _JobState:
    export_id: str
    status: JobStatus = "pending"
    progress: list[ProgressEvent] = field(default_factory=list)
    counts: dict[str, int] | None = None
    error_count: int | None = None
    warning_count: int | None = None
    destination: str | None = None
    reason: str | None = None
    #: Bug 2 de la 3ra ronda de revision de M3: se activa en el `finally` del hilo
    #: REAL que corre `convert()` (`_run_job::run_sync`), sea cual sea el motivo
    #: (exito, excepcion, o terminar tarde despues de que `asyncio.wait_for` ya
    #: desistio por timeout) - NUNCA cuando el orquestador async decide dejar de
    #: esperarlo. `default_factory` para que cada job tenga el suyo propio.
    finished_event: threading.Event = field(default_factory=threading.Event)


class JobStore:
    """`job_id -> _JobState`, en memoria y protegido por un lock (mismo espiritu que
    `services.exports.ExportStore`: nombres que no atan la implementacion a "es un
    dict", para poder pasar a SQLite despues sin tocar quien la usa).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, _JobState] = {}

    def create(self, job_id: str, export_id: str) -> None:
        with self._lock:
            self._jobs[job_id] = _JobState(export_id=export_id)

    @staticmethod
    def _is_active(job: _JobState) -> bool:
        """Bug 2 de la 3ra ronda de revision de M3: "activo" ya no es solo el ESTADO
        del job. Un job `pending`/`running` siempre lo es (el hilo real todavia esta
        corriendo, por definicion). Un job `failed` con motivo `timeout` TAMBIEN lo es
        MIENTRAS su `finished_event` no se haya activado: el job ya se dio por
        perdido, pero el hilo real de `asyncio.to_thread(run_sync)` sigue vivo y
        escribiendo en `_output/` (no se puede matar, limitacion de Python) hasta que
        `convert()` termine sola. Cualquier otro `failed` (un error real de
        parseo/IO) no tiene ningun hilo corriendo detras y nunca es activo."""
        if job.status in _ACTIVE_JOB_STATUSES:
            return True
        return (
            job.status == "failed"
            and job.reason == TIMEOUT_REASON
            and not job.finished_event.is_set()
        )

    def find_active_job_id(self, export_id: str) -> str | None:
        """`job_id` de un job activo de `export_id` (ver `_is_active`), o `None` si no
        hay ninguno. Usado tanto por `start_conversion` (evitar 2 conversiones
        concurrentes sobre el mismo export, observacion 1) como por
        `services/lifecycle.py::delete_export` (evitar borrar mientras una conversion
        sigue escribiendo, observacion 2)."""
        with self._lock:
            for job_id, job in self._jobs.items():
                if job.export_id == export_id and self._is_active(job):
                    return job_id
            return None

    def create_if_no_active_job(self, job_id: str, export_id: str) -> str | None:
        """Version ATOMICA (bajo un unico `with self._lock`) de "mirar si hay un job
        activo y, si no, crear uno": separar el chequeo (`find_active_job_id`) de la
        creacion (`create`) en dos llamadas dejaria una ventana TOCTOU donde dos
        `POST /convert` concurrentes podrian pasar el chequeo antes de que cualquiera
        de los dos creara su job. Devuelve `None` si `job_id` quedo creado, o el
        `job_id` del job activo existente si no se creo nada. El chequeo de
        `_is_active` (incluido el `finished_event` de un job vencido por timeout, bug
        2) corre bajo el MISMO lock, sin ventana nueva de carrera."""
        with self._lock:
            for existing_id, job in self._jobs.items():
                if job.export_id == export_id and self._is_active(job):
                    return existing_id
            self._jobs[job_id] = _JobState(export_id=export_id)
            return None

    def get_finished_event(self, job_id: str) -> threading.Event | None:
        """El `threading.Event` real del hilo que corre (o corrio) `convert()` para
        `job_id`, o `None` si el job no existe. Deliberadamente NO expuesto en
        `JobView`/`GET /jobs/{id}` (es un detalle interno de sincronizacion, no algo
        que le importe a un cliente HTTP): sirve para que `_run_job` lo active desde
        DENTRO del hilo real (bug 2) y para que los tests esperen el fin real del
        hilo sin usar un sleep arbitrario."""
        with self._lock:
            job = self._jobs.get(job_id)
            return job.finished_event if job is not None else None

    def mark_running(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.status = "running"

    def append_progress(self, job_id: str, category: str, done: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.progress.append(ProgressEvent(category=category, done=done))

    def mark_done(
        self,
        job_id: str,
        *,
        counts: dict[str, int],
        error_count: int,
        warning_count: int,
        destination: str,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.status = "done"
                job.counts = dict(counts)
                job.error_count = error_count
                job.warning_count = warning_count
                job.destination = destination

    def mark_failed(self, job_id: str, reason: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.status = "failed"
                job.reason = reason

    def remove_by_export(self, export_id: str) -> None:
        """Olvida todos los jobs de `export_id` (usado por `DELETE /exports/{id}`,
        services/lifecycle.py): un export borrado no debe dejar jobs `GET /jobs/{id}`
        respondiendo sobre un directorio que ya no existe."""
        with self._lock:
            stale = [job_id for job_id, job in self._jobs.items() if job.export_id == export_id]
            for job_id in stale:
                del self._jobs[job_id]

    def get(self, job_id: str) -> JobView | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return JobView(
                job_id=job_id,
                export_id=job.export_id,
                status=job.status,
                progress=tuple(job.progress),
                counts=dict(job.counts) if job.counts is not None else None,
                error_count=job.error_count,
                warning_count=job.warning_count,
                destination=job.destination,
                reason=job.reason,
            )


_store = JobStore()


def get_job_store() -> JobStore:
    """Unico punto de acceso al store (facilita reemplazarlo en tests si hiciera falta)."""
    return _store


#: Referencias fuertes a las tareas de fondo en curso: sin esto `asyncio` puede
#: recolectar la tarea (y cancelarla en silencio) apenas termina esta funcion, porque
#: nada mas la esta "sosteniendo" (patron documentado en la guia de `asyncio.create_task`).
_background_tasks: set[asyncio.Task[None]] = set()


def _find_job_or_404(job_id: str) -> JobView:
    view = get_job_store().get(job_id)
    if view is None:
        raise ProblemError(
            status=404, title="Job no encontrado", detail=f"No existe ningun job con id '{job_id}'."
        )
    return view


def ensure_job_exists(job_id: str) -> None:
    """Lanza 404 si `job_id` no existe; no hace nada mas (para chequear ANTES del SSE)."""
    _find_job_or_404(job_id)


def job_status(job_id: str) -> JobView:
    """`GET /jobs/{id}`: 404 si no existe, la foto actual si existe."""
    return _find_job_or_404(job_id)


def start_conversion(export_id: str, *, templates: str | None, only: list[str] | None) -> str:
    """`POST /exports/{id}/convert`: valida, registra el job y lo lanza en segundo plano.

    Nunca espera a que la conversion termine (CA-2): crea la tarea de asyncio y
    devuelve el `job_id` de inmediato. `only` esta documentado en el spec pero
    `usecases.convert.convert()` de core todavia no filtra categorias (mismo pendiente
    que `--only` del CLI, ver docs/specs/05-cli.md y STATUS.md): se acepta el campo
    para no romper el contrato, se registra un warning, y no tiene efecto todavia.
    """
    source_dir = exports_service.export_directory(export_id)  # 404 si no existe
    if only:
        logger.warning(
            "POST /convert: 'only'=%r fue ignorado (core.convert() todavia no filtra "
            "categorias; ver docs/specs/05-cli.md y STATUS.md).",
            only,
        )
    output_dir = exports_service.output_directory(export_id)

    job_id = str(uuid.uuid4())
    # Observacion 1 de la revision de M3: sin este chequeo ATOMICO, varios
    # `POST /convert` seguidos sobre el MISMO export lanzaban varios jobs que
    # escribian CONCURRENTEMENTE el mismo `_output/` (reproducido por el reviewer con
    # 3 POST seguidos). Si ya hay un job `pending`/`running` para este export, se
    # devuelve 409 con el `job_id` existente en vez de crear otro.
    existing_job_id = get_job_store().create_if_no_active_job(job_id, export_id)
    if existing_job_id is not None:
        raise ProblemError(
            status=409,
            title="Conversion en curso",
            detail=(
                f"Ya hay una conversion pendiente o en curso para el export "
                f"'{export_id}' (job '{existing_job_id}'). Esperala (GET "
                "/jobs/{id}) antes de lanzar otra."
            ),
        )
    timeout = job_timeout_seconds()

    task = asyncio.create_task(_run_job(job_id, source_dir, output_dir, templates, timeout))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return job_id


async def _run_job(
    job_id: str,
    source_dir: Path,
    output_dir: Path,
    templates: str | None,
    timeout: float,
) -> None:
    store = get_job_store()
    store.mark_running(job_id)
    # Bug 2 de la 3ra ronda de revision de M3: el job ya se creo (`create_if_no_active_job`,
    # en `start_conversion`) antes de programar esta tarea, asi que su `finished_event`
    # existe siempre en este punto.
    finished_event = store.get_finished_event(job_id)
    assert finished_event is not None, f"job {job_id} deberia existir en el store"

    def on_progress(category: str, done: int) -> None:
        # Se llama DESDE EL THREAD de `asyncio.to_thread` (ver docstring del modulo).
        store.append_progress(job_id, category, done)

    def run_sync() -> Any:
        try:
            source = create_source(source_dir)
            sink = FilesystemSink(output_dir)
            return run_convert(
                source,
                sink,
                templates=templates,
                overwrite=True,
                progress=on_progress,
            )
        finally:
            # Se activa en el `finally` del hilo REAL (corre DENTRO de
            # `asyncio.to_thread`), sea cual sea el motivo: exito, excepcion, o
            # terminar tarde despues de que `asyncio.wait_for` ya desistio por
            # timeout mas abajo. Nunca cuando el orquestador async decide dejar de
            # esperarlo - ese es justo el bug que esto arregla.
            finished_event.set()

    try:
        result = await asyncio.wait_for(asyncio.to_thread(run_sync), timeout=timeout)
    except TimeoutError:
        store.mark_failed(job_id, TIMEOUT_REASON)
        return
    except Exception as exc:  # el job puede fallar por mil motivos de datos/IO
        logger.warning("Job %s fallo: %s", job_id, exc)
        store.mark_failed(job_id, str(exc))
        return

    store.mark_done(
        job_id,
        counts=result.counts,
        error_count=result.error_count,
        warning_count=result.warning_count,
        destination=result.destination,
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_job_events(job_id: str, request: Request) -> AsyncIterator[str]:
    """Generador del cuerpo de `GET /jobs/{id}/events` (spec 06 CA-3).

    Llamar a esto SOLO despues de `ensure_job_exists` (el router lo hace antes de
    construir el `StreamingResponse`): un 404 lanzado desde dentro de un generador ya
    en curso llega tarde, con la respuesta ya empezada.

    Si el job ya termino cuando el cliente se conecta, manda de una el evento final
    (`done`/`error`) y corta: no lo deja esperando eventos que ya pasaron. Si el
    cliente se desconecta a mitad de camino, el generador corta (la conversion sigue
    sola en segundo plano; lo unico que no puede pasar es este generador quedando vivo
    para siempre sin que nadie lo lea).
    """
    sent = 0
    while True:
        if await request.is_disconnected():
            return
        view = get_job_store().get(job_id)
        if view is None:
            return
        while sent < len(view.progress):
            event = view.progress[sent]
            sent += 1
            yield _sse("progress", {"category": event.category, "done": event.done})
        if view.status == "done":
            # Observacion 3 de la revision de M3: `GET /jobs/{id}` (JobStatusResponse,
            # schemas/jobs.py) deliberadamente NO incluye `destination` (una ruta
            # absoluta del SERVIDOR) - filtrarla aca en el SSE era inconsistente y una
            # fuga de la estructura de directorios interna hacia cualquier cliente.
            yield _sse(
                "done",
                {
                    "counts": view.counts,
                    "errors": view.error_count,
                    "warnings": view.warning_count,
                },
            )
            return
        if view.status == "failed":
            yield _sse("error", {"reason": view.reason})
            return
        await asyncio.sleep(_POLL_INTERVAL_S)


__all__ = [
    "DEFAULT_JOB_TIMEOUT_S",
    "JOB_TIMEOUT_ENV",
    "TIMEOUT_REASON",
    "JobStore",
    "JobView",
    "ProgressEvent",
    "ensure_job_exists",
    "get_job_store",
    "job_status",
    "job_timeout_seconds",
    "start_conversion",
    "stream_job_events",
]
