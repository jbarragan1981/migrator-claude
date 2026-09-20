"""`DELETE /exports/{id}` (spec 06, tercera ronda de M3).

Vive en su propio modulo (no en `services/exports.py`) porque necesita conocer TANTO
`ExportStore` como `JobStore`: si viviera en `exports.py`, este pasaria a importar
`jobs.py`, que YA importa `exports.py` (`services/jobs.py::start_conversion` usa
`exports_service.export_directory`/`output_directory`) - un ciclo. Ninguno de los dos
modulos importa `lifecycle.py`, asi que no hay vuelta.

Decisiones de este modulo:

* **`export_id` inexistente -> 404.** Spec 06 no lo aclara (deja la eleccion entre
  404 y "204 idempotente" a criterio de quien implementa). Se elige 404 por
  consistencia: cada otro endpoint sobre un `export_id` que no existe responde 404
  (`export_directory`, `output_directory`, `/convert`) y un DELETE no tiene motivo
  para ser la unica excepcion silenciosa del contrato. Un cliente que quiera un
  DELETE "a ciegas" (sin chequear antes si existe) puede tratar el 404 como exito.
* **Modo subida (`owned=True`) -> se borra el directorio de trabajo COMPLETO**
  (`shutil.rmtree`). Es enteramente nuestro: vive bajo `CEM_WORK_DIR`, lo creamos en
  `register_upload` (services/exports.py) y nadie mas lo usa.
* **Modo local (`owned=False`) -> SOLO se borra `_output/`, nunca la carpeta del
  usuario.** La ruta registrada con `{"path": "..."}` es del USUARIO (su export
  original, en su disco): `register_local_path` (services/exports.py) la lee pero
  jamas la mueve ni la borra, y `DELETE` respeta la misma regla. Lo unico que
  `POST /convert` crea DENTRO de esa carpeta es `_output/` (services/jobs.py); eso si
  es nuestro y se borra. Si `_output/` no llego a existir (nunca se convirtio), no hay
  nada que borrar ahi y no es un error.
* En los dos modos, al final se olvida el registro en `ExportStore` y cualquier job
  de `JobStore` asociado a ese `export_id` (`GET /jobs/{id}` no tiene sentido sobre un
  export que ya no existe).
* **El borrado es best-effort pero YA NO es silencioso del lado del servidor**
  (bug 1, parte 4 de la 3ra ronda de revision de M3): `_rmtree_best_effort` reemplaza
  `shutil.rmtree(path, ignore_errors=True)` por `shutil.rmtree(path, onexc=...)`, con
  un callback que registra cada archivo/carpeta que no se pudo quitar via
  `logger.warning`. El `DELETE` sigue respondiendo `204` igual en cualquier caso (no
  se cambia el contrato ya publicado) - lo que cambia es que un borrado parcial (por
  ejemplo, un archivo que el hilo `cem-zip-writer` de `services/output.py` todavia
  tiene abierto) ya queda anotado en el log en vez de desaparecer sin dejar rastro.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from claude_export_md_api.errors import ProblemError
from claude_export_md_api.services import exports as exports_service
from claude_export_md_api.services import jobs as jobs_service

logger = logging.getLogger(__name__)


def _log_rmtree_failure(function: object, path: str, excinfo: BaseException) -> None:
    """`onexc` de `shutil.rmtree` (soportado desde Python 3.12, la version que pide
    `pyproject.toml`): a diferencia de `ignore_errors=True`, que traga cualquier fallo
    en silencio, esto deja constancia en el log del servidor de que ALGO no se pudo
    borrar. Bug 1, parte 4 de la 3ra ronda de revision de M3: el hilo `cem-zip-writer`
    de `services/output.py` podia quedar (antes del fix de ese modulo) con un archivo
    abierto dentro de este directorio; `DELETE` respondia `204` igual con el borrado
    parcial, sin ningun aviso de que quedaron datos del usuario abandonados en disco.
    El `DELETE` sigue respondiendo `204` en cualquier caso (no se cambia el contrato
    ya publicado): esto SOLO deja de ser silencioso del lado del servidor.
    """
    logger.warning(
        "No se pudo borrar '%s' durante un DELETE (%s): %s",
        path,
        getattr(function, "__name__", function),
        excinfo,
    )


def _rmtree_best_effort(path: Path) -> None:
    """Mismo contrato que `shutil.rmtree(path, ignore_errors=True)` (nunca lanza),
    pero cada fallo individual se registra en vez de desaparecer sin dejar rastro."""
    shutil.rmtree(path, onexc=_log_rmtree_failure)


def delete_export(export_id: str) -> None:
    """`DELETE /exports/{id}`: ver decisiones del modulo. No hay valor de retorno:
    el router responde `204` sin body."""
    store = exports_service.get_store()
    # Se USA `get` (no destructivo) en vez de `remove` directo: hace falta poder
    # chequear si hay una conversion en curso (observacion 2 de la revision de M3)
    # ANTES de decidir si de verdad se borra el registro.
    record = store.get(export_id)
    if record is None:
        raise ProblemError(
            status=404,
            title="Export no encontrado",
            detail=f"No existe ningun export con id '{export_id}'.",
        )

    # Observacion 2 de la revision de M3: sin este chequeo, `DELETE` borraba el
    # registro con 204 pero el thread de la conversion en curso (`services/jobs.py`)
    # seguia escribiendo - y de hecho RECREABA `_output/` DESPUES del borrado, o
    # fallaba a mitad de camino si el modo subida ya habia borrado el directorio
    # entero (reproducido por el reviewer). Rechazar con 409 en vez de un borrado que
    # compite con una escritura en curso.
    active_job_id = jobs_service.get_job_store().find_active_job_id(export_id)
    if active_job_id is not None:
        raise ProblemError(
            status=409,
            title="Conversion en curso",
            detail=(
                f"El export '{export_id}' tiene una conversion pendiente o en curso "
                f"(job '{active_job_id}'). Esperala (GET /jobs/{{id}}) antes de "
                "borrar el export."
            ),
        )

    store.remove(export_id)

    if record.owned:
        # Subida: el directorio ENTERO (bajo CEM_WORK_DIR) es nuestro.
        _rmtree_best_effort(record.path)
    else:
        # Modo local: la carpeta es del usuario. Solo se borra lo que creamos nosotros.
        output_dir = record.path / exports_service.OUTPUT_DIRNAME
        if output_dir.is_dir():
            _rmtree_best_effort(output_dir)

    jobs_service.get_job_store().remove_by_export(export_id)


__all__ = ["delete_export"]
