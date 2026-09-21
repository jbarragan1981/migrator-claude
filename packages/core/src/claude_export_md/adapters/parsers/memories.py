"""Parser de `memories` (spec 03, sección `memories`).

Lo que confirmó la Fase 0 (`docs/export-format/memories.md`) y corrige la hipótesis de
CLAUDE.md §§2/5/6: `memories` NO es una carpeta de archivos `.md`, es **un único JSON por
cuenta** (`memories-000/memories/<account_uuid>.json`) con tres orígenes de memoria
dentro:

* `memory_files[]` — la única con `path` y `updated_at` propios (CA-2);
* `conversations_memory` — una cadena a nivel de cuenta (CA-3);
* `project_memories{}` — una cadena por proyecto, indexada por uuid (CA-4).

Las tres se representan con la misma entidad `Memory`; las dos últimas reciben la ruta
sintética que define el dominio (ADR-0005), nunca una inventada aquí.

Sobre `json.load`: este archivo ronda los 100 KB en el export real (110.955 bytes), es un
objeto (no un array de ítems) y hay exactamente uno por cuenta, así que leerlo entero es
correcto y mucho más simple que `ijson`. La regla de streaming (CA-C3) apunta a
`conversations.json`, que pesa ~98 MB. Aun así se comprueba el tamaño antes de leer:
si algún export trajera un `memories.json` desproporcionado, se registra el problema en
`Report` en vez de cargarlo en memoria.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from claude_export_md.domain.entities import (
    Memory,
    Report,
    conversations_memory,
    memory_from_file,
    project_memory,
)
from claude_export_md.errors import CorruptFileError
from claude_export_md.ports.source import JSON, ExportSource, SourceFile

logger = logging.getLogger(__name__)

#: Nombre de la categoría tal como la nombran el manifiesto y `ExportSource`.
CATEGORY = "memories"

#: Techo para leer el archivo entero (CA-C3). Por encima se registra y no se carga.
MAX_JSON_BYTES = 10 * 1024 * 1024

#: Claves del JSON de la cuenta.
KEY_MEMORY_FILES = "memory_files"
KEY_CONVERSATIONS_MEMORY = "conversations_memory"
KEY_PROJECT_MEMORIES = "project_memories"


def parse(source: ExportSource, report: Report) -> Iterator[Memory]:
    """Memorias del export, en orden estable y sin repetir `path` (CA-C1, CA-C5).

    No lanza: un archivo ilegible o un ítem con forma inesperada se acumula en
    `report.errors` y el resto sigue (CA-C2).
    """
    seen: set[str] = set()
    for file in _files(source, report):
        data = _load(source, file, report)
        if data is None:
            continue
        for memory in _memories_of(data, file, report):
            if memory.path in seen:
                report.add_warning(
                    f"{file.path}: memoria repetida {memory.path}; se conserva la primera"
                )
                continue
            seen.add(memory.path)
            report.count(CATEGORY)
            yield memory


# ------------------------------------------------------------------- archivos


def _files(source: ExportSource, report: Report) -> list[SourceFile]:
    """Archivos JSON de la categoría, ordenados por parte y ruta (CA-C1)."""
    files = [file for file in source.files() if file.category == CATEGORY]
    for file in files:
        if file.kind != JSON:
            # La hipótesis de la carpeta de .md quedó descartada, pero si un export
            # trae algo así no se descarta en silencio (CLAUDE.md §1.3).
            report.add_warning(
                f"{file.path}: no es JSON; en este formato las memorias viajan "
                "en un único JSON por cuenta, se omite"
            )
    return sorted((file for file in files if file.kind == JSON), key=lambda f: (f.part, f.path))


def _load(source: ExportSource, file: SourceFile, report: Report) -> dict[str, Any] | None:
    """Contenido del JSON de la cuenta, o `None` si no se pudo leer (ya registrado)."""
    if file.bytes > MAX_JSON_BYTES:
        report.add_error(
            CATEGORY,
            f"el archivo ocupa {file.bytes} bytes, por encima del límite de "
            f"{MAX_JSON_BYTES} bytes para leerlo entero; se omite",
            source_file=file.path,
        )
        return None
    try:
        with source.open_file(file) as stream:
            data = json.load(stream)
    except (CorruptFileError, OSError, UnicodeDecodeError, ValueError) as exc:
        logger.warning("Memorias ilegibles en %s: %s", file.path, exc)
        report.add_error(CATEGORY, f"JSON ilegible: {exc}", source_file=file.path)
        return None
    if not isinstance(data, dict):
        report.add_error(
            CATEGORY,
            f"la raíz del JSON es {type(data).__name__}, se esperaba un objeto",
            source_file=file.path,
        )
        return None
    return data


# ------------------------------------------------------------------- memorias


def _memories_of(data: Mapping[str, Any], file: SourceFile, report: Report) -> Iterator[Memory]:
    """Las tres formas de memoria del archivo, en orden estable."""
    yield from _from_memory_files(data.get(KEY_MEMORY_FILES), file, report)
    yield from _from_conversations_memory(data.get(KEY_CONVERSATIONS_MEMORY), file, report)
    yield from _from_project_memories(data.get(KEY_PROJECT_MEMORIES), file, report)


def _from_memory_files(raw: Any, file: SourceFile, report: Report) -> Iterator[Memory]:  # noqa: ANN401
    """CA-2: una `Memory` por entrada, con su ruta real. CA-5: ausente o vacío vale."""
    if raw is None:
        return
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        _report_shape(report, file, KEY_MEMORY_FILES, raw, "un array")
        return
    for index, entry in enumerate(raw):
        item_id = f"{KEY_MEMORY_FILES}[{index}]"
        if not isinstance(entry, Mapping):
            _report_shape(report, file, item_id, entry, "un objeto")
            continue
        if not isinstance(entry.get("path"), str) or not entry["path"].strip():
            # Sin `path` no hay identificador (ADR-0005): se registra con su posición
            # para que el usuario pueda ir a buscarlo, no se inventa una ruta.
            report.add_error(
                CATEGORY,
                "entrada de memory_files sin `path`: no se puede identificar",
                item_id=item_id,
                source_file=file.path,
            )
            continue
        yield _tagged(memory_from_file(entry), file)


def _from_conversations_memory(raw: Any, file: SourceFile, report: Report) -> Iterator[Memory]:  # noqa: ANN401
    """CA-3: la memoria de conversaciones, con la ruta sintética del dominio."""
    if raw is None or raw == "":
        return
    if not isinstance(raw, str):
        _report_shape(report, file, KEY_CONVERSATIONS_MEMORY, raw, "texto")
        return
    yield _tagged(conversations_memory(raw), file)


def _from_project_memories(raw: Any, file: SourceFile, report: Report) -> Iterator[Memory]:  # noqa: ANN401
    """CA-4: una `Memory` por proyecto, ordenadas por uuid para que el orden sea estable."""
    if raw is None:
        return
    if not isinstance(raw, Mapping):
        _report_shape(report, file, KEY_PROJECT_MEMORIES, raw, "un objeto")
        return
    for project_id in sorted(raw):
        content = raw[project_id]
        if not isinstance(content, str):
            _report_shape(report, file, str(project_id), content, "texto")
            continue
        if content == "":
            continue
        yield _tagged(project_memory(str(project_id), content), file)


# ------------------------------------------------------------------ auxiliares


def _tagged(memory: Memory, file: SourceFile) -> Memory:
    """Anota de qué archivo del export salió la memoria.

    Va en `extra` (`extra="allow"`) porque `source_file` es un dato de procedencia, no
    del export: el render lo saca de ahí para el frontmatter obligatorio (spec 04) sin
    que el dominio tenga que conocer el sistema de archivos.
    """
    return Memory.model_validate({**memory.model_dump(), "source_file": file.path})


def _report_shape(
    report: Report, file: SourceFile, item_id: str, value: Any, expected: str
) -> None:  # noqa: ANN401
    report.add_error(
        CATEGORY,
        f"se esperaba {expected} y vino {type(value).__name__}",
        item_id=item_id,
        source_file=file.path,
    )


__all__ = ["CATEGORY", "MAX_JSON_BYTES", "parse"]
