"""Parser de `projects` (spec 03, sección `projects`).

Lo que confirmó la Fase 0 (`docs/export-format/projects.md`) y corrige la hipótesis del
spec 01: `projects` NO es un `projects.json` con un array, son **N archivos JSON, uno por
proyecto** (`projects-000/projects/<uuid>.json`, 32 en el export observado y 22 KB en
total). Cada archivo es un objeto con `uuid`, `name`, `description`, `is_private`,
`is_starter_project`, `prompt_template`, `created_at`, `updated_at`, `creator` y `docs[]`.

Decisiones de este módulo:

* **`prompt_template` → `Project.instructions` (CA-2)** — `""` es un valor del export
  (instrucciones vacías) y NO se convierte a `None`: solo la ausencia de la clave deja el
  campo en `None`. En el export observado está vacío en los 3 proyectos de la muestra.
* **`docs[]` sin contenido (CA-3)** — el export solo trae `uuid`, `filename` y
  `created_at` de cada documento; el texto no viaja en esta categoría y todavía no se
  sabe dónde vive (`docs/export-format/projects.md`, sección Dudas). Cada entrada produce
  un `ProjectDoc` con `content=None` —que por ADR-0005 significa *no está en el export*,
  distinto de `""`—. Nunca se inventa contenido ni se deja vacío en silencio
  (CLAUDE.md §1.3): el `.md` de cada documento lo dice, y en `report.warnings` queda UNA
  advertencia agregada por corrida (`{docs} de {projects} llegan solo con su metadata`),
  no una por documento — mismo criterio que `ORPHAN_PROJECTS_WARNING` en
  `usecases/links.py`, porque 32 proyectos producían 32 líneas idénticas que tapaban en
  el resumen del CLI a las advertencias realmente accionables. Se cuenta en `parse()`,
  después del dedupe, para no nombrar documentos de proyectos que se descartan. Si un
  export futuro trajera `content` como texto, se usa tal cual y no se cuenta.
* **`conversation_ids` se deja vacío (CA-4)** — el archivo de un proyecto no lista sus
  conversaciones; el enlace va al revés, desde `conversations[].project_uuid`. Poblarlo
  aquí exigiría leer los ~98 MB de `conversations.json` dentro de este parser. Lo resuelve
  quien tenga las dos colecciones delante (`usecases/convert.py`).
* **`creator` es un objeto (CA-5)** — se toma `creator.uuid` como `creator_id` y el resto
  del objeto (`full_name`) se conserva en `extra["creator"]`, sin duplicar el uuid. Si
  `creator` llegara con otra forma no se asume que sea el id plano: queda en
  `extra["creator_raw"]` con una advertencia, igual que `settings` en `light_metadata`.
* **Raíz que es un array** — es la forma del formato legacy (`projects.json`). Se lee como
  varios proyectos con una advertencia, para no devolver cero en silencio.
* **`json.load` con techo** — mismo criterio que `memories` y `light_metadata`: aquí cada
  archivo pesa menos de 1 KB y hay uno por proyecto. La regla de streaming (CA-C3) apunta
  a `conversations.json`; aun así se comprueba el tamaño antes de leer.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from claude_export_md.domain.entities import Project, ProjectDoc, Report
from claude_export_md.errors import CorruptFileError
from claude_export_md.ports.source import JSON, ExportSource, SourceFile

logger = logging.getLogger(__name__)

#: Nombre de la categoría tal como la nombran el manifiesto y `ExportSource`.
CATEGORY = "projects"

#: Techo para leer un archivo entero (CA-C3). Por encima se registra y no se carga.
MAX_JSON_BYTES = 10 * 1024 * 1024

#: Claves del archivo de un proyecto que el parser mapea a un campo de `Project`.
KEY_UUID = "uuid"
KEY_NAME = "name"
KEY_DESCRIPTION = "description"
KEY_PROMPT_TEMPLATE = "prompt_template"
KEY_CREATED_AT = "created_at"
KEY_UPDATED_AT = "updated_at"
KEY_CREATOR = "creator"
KEY_DOCS = "docs"
_PROJECT_KEYS = frozenset(
    {
        KEY_UUID,
        KEY_NAME,
        KEY_DESCRIPTION,
        KEY_PROMPT_TEMPLATE,
        KEY_CREATED_AT,
        KEY_UPDATED_AT,
        KEY_CREATOR,
        KEY_DOCS,
    }
)

#: Claves de una entrada de `docs[]` que el parser mapea a un campo de `ProjectDoc`.
KEY_FILENAME = "filename"
KEY_CONTENT = "content"
_DOC_KEYS = frozenset({KEY_UUID, KEY_FILENAME, KEY_CREATED_AT, KEY_CONTENT})

#: Prefijo con el que se identifica un ítem cuando la raíz es un array (formato legacy).
ITEM_PREFIX = "item"
#: Campo de `extra` que anota de qué archivo del export salió el proyecto (spec 04).
SOURCE_FILE_KEY = "source_file"
#: Marca de un doc al que hubo que darle un identificador (ver `_doc`).
SYNTHETIC_ID_KEY = "synthetic_id"

#: Advertencia de CA-3, UNA por corrida: el export no trae el texto de los documentos.
#: `{docs}` y `{projects}` llegan ya pluralizados (`1 documento` / `3 documentos`).
DOCS_WITHOUT_CONTENT_WARNING = (
    "{docs} de {projects} {verb} solo con su metadata; el contenido no está en este "
    "export (cada documento lo dice en su propio archivo)"
)
#: Advertencia de un doc sin `uuid` propio (ver `_doc`).
DOC_WITHOUT_ID_WARNING = (
    "{file}: el documento {item} del proyecto {project} no trae `uuid`; "
    "se le da el identificador sintético {doc}"
)

#: Fecha de relleno para ordenar: solo se usa como desempate, nunca se escribe.
_NO_DATE = datetime.min.replace(tzinfo=UTC)


def parse(source: ExportSource, report: Report) -> Iterator[Project]:
    """Proyectos del export, un archivo cada uno y sin repetir `uuid` (CA-1, CA-C1).

    No lanza: un archivo ilegible o un ítem con forma inesperada se acumula en
    `report.errors` y el resto sigue (CA-C2).

    La advertencia de CA-3 se cuenta aquí, sobre los proyectos que de verdad se emiten, y
    se escribe una sola vez al terminar: dentro de `_doc` nombraba documentos de un
    proyecto repetido que el dedupe descartaba después, y el informe hablaba de archivos
    que nunca se escribieron.
    """
    seen: set[str] = set()
    docs_without_content = 0
    projects_without_content = 0
    for file in _files(source, report):
        data = _load(source, file, report)
        if data is None:
            continue
        for item_id, raw in _items(data, file, report):
            project = _project(raw, item_id, file, report)
            if project is None:
                continue
            if project.id in seen:
                report.add_warning(
                    f"{file.path}: proyecto repetido {project.id}; se conserva el primero"
                )
                continue
            seen.add(project.id)
            report.count(CATEGORY)
            missing = sum(1 for doc in project.docs if doc.content is None)
            docs_without_content += missing
            projects_without_content += 1 if missing else 0
            yield project
    if docs_without_content:
        report.add_warning(_docs_without_content(docs_without_content, projects_without_content))


def parse_sorted(source: ExportSource, report: Report) -> list[Project]:
    """Los mismos proyectos ya ordenados por `created_at` y luego `id` (CA-C5).

    `parse` emite en el orden de los archivos, que ya es determinista; este es el orden
    canónico de la colección, el que necesita el `_index.md`. Los proyectos sin fecha van
    al final (no se les inventa una), ordenados entre sí por `id`.
    """
    return sorted(parse(source, report), key=sort_key)


def sort_key(project: Project) -> tuple[bool, datetime, str]:
    """Clave de orden canónico de un proyecto (CA-C5)."""
    created = project.created_at
    return (created is None, created or _NO_DATE, project.id)


def _docs_without_content(docs: int, projects: int) -> str:
    """CA-3 en una línea: cuántos documentos, de cuántos proyectos, llegan sin texto."""
    return DOCS_WITHOUT_CONTENT_WARNING.format(
        docs=_plural(docs, "documento", "documentos"),
        projects=_plural(projects, "proyecto", "proyectos"),
        verb="llega" if docs == 1 else "llegan",
    )


def _plural(count: int, singular: str, plural: str) -> str:
    """`1 documento` / `3 documentos` (mismo criterio que el resumen del CLI)."""
    return f"{count} {singular if count == 1 else plural}"


# ------------------------------------------------------------------- archivos


def _files(source: ExportSource, report: Report) -> list[SourceFile]:
    """Archivos JSON de la categoría, ordenados por parte y ruta (CA-C1, CA-C5)."""
    files = [file for file in source.files() if file.category == CATEGORY]
    for file in files:
        if file.kind != JSON:
            report.add_warning(f"{file.path}: no es JSON; se omite")
    return sorted((file for file in files if file.kind == JSON), key=lambda f: (f.part, f.path))


def _load(source: ExportSource, file: SourceFile, report: Report) -> Any | None:  # noqa: ANN401
    """Contenido del JSON, o `None` si no se pudo leer (ya registrado en `Report`)."""
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
            return json.load(stream)
    except (CorruptFileError, OSError, UnicodeDecodeError, ValueError) as exc:
        logger.warning("Proyecto ilegible en %s: %s", file.path, exc)
        report.add_error(CATEGORY, f"JSON ilegible: {exc}", source_file=file.path)
        return None


def _items(data: Any, file: SourceFile, report: Report) -> list[tuple[str | None, Any]]:  # noqa: ANN401
    """Los proyectos del archivo: el objeto (CA-1) o, en legacy, los ítems del array.

    El `item_id` es `None` cuando el archivo ES el proyecto: ahí el que identifica al ítem
    en `Report` es el propio `source_file`, y un `item[0]` solo sería ruido.
    """
    if isinstance(data, Mapping):
        return [(None, data)]
    if isinstance(data, Sequence) and not isinstance(data, str | bytes):
        report.add_warning(
            f"{file.path}: la raíz del JSON es un array y se esperaba un proyecto por "
            "archivo; se leen todos sus ítems como proyectos"
        )
        return [(f"{ITEM_PREFIX}[{index}]", raw) for index, raw in enumerate(data)]
    report.add_error(
        CATEGORY,
        f"la raíz del JSON es {type(data).__name__}, se esperaba un objeto con el proyecto",
        source_file=file.path,
    )
    return []


# ------------------------------------------------------------------- proyecto


def _project(
    raw: Any,  # noqa: ANN401 - lo que venga en el archivo del export
    item_id: str | None,
    file: SourceFile,
    report: Report,
) -> Project | None:
    """El objeto del archivo → `Project`, o `None` si no se pudo identificar (CA-C2)."""
    if not isinstance(raw, Mapping):
        report.add_error(
            CATEGORY,
            f"se esperaba un objeto y vino {type(raw).__name__}",
            item_id=item_id,
            source_file=file.path,
        )
        return None
    uuid = raw.get(KEY_UUID)
    if not isinstance(uuid, str) or not uuid.strip():
        report.add_error(
            CATEGORY,
            "proyecto sin `uuid`: no se puede identificar",
            item_id=item_id,
            source_file=file.path,
        )
        return None
    values = {str(key): value for key, value in raw.items() if key not in _PROJECT_KEYS}
    values.update(
        id=uuid,
        name=_text(raw.get(KEY_NAME)),
        description=_text(raw.get(KEY_DESCRIPTION)),
        # CA-2: `""` es un valor, no una ausencia; solo la clave ausente da `None`.
        instructions=_text(raw.get(KEY_PROMPT_TEMPLATE)),
        created_at=raw.get(KEY_CREATED_AT),
        updated_at=raw.get(KEY_UPDATED_AT),
        creator_id=_creator(raw.get(KEY_CREATOR), uuid, file, report, values),
        docs=_docs(raw.get(KEY_DOCS), uuid, file, report),
        # CA-4: el archivo del proyecto no lista sus conversaciones; el enlace vive en
        # `conversations[].project_uuid` y lo resuelve quien tenga ambas colecciones.
        conversation_ids=[],
    )
    values.setdefault(SOURCE_FILE_KEY, file.path)
    return Project.model_validate(values)


def _text(value: Any) -> str | None:  # noqa: ANN401 - valor libre del export
    """Solo se acepta texto; cualquier otra forma deja el campo vacío, no el proyecto."""
    return value if isinstance(value, str) else None


def _creator(
    raw: Any,  # noqa: ANN401 - valor libre del export
    project_id: str,
    file: SourceFile,
    report: Report,
    extra: dict[str, Any],
) -> str | None:
    """CA-5: `creator.uuid` como referencia; el resto del objeto se conserva en `extra`."""
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        rest = {str(key): value for key, value in raw.items() if key != KEY_UUID}
        if rest:
            extra[KEY_CREATOR] = rest
        uuid = raw.get(KEY_UUID)
        return uuid if isinstance(uuid, str) and uuid.strip() else None
    # No se asume que `creator` sea el uuid plano (CA-5): se conserva y se avisa.
    extra[f"{KEY_CREATOR}_raw"] = raw
    report.add_warning(
        f"{file.path}: `{KEY_CREATOR}` del proyecto {project_id} debería ser un objeto "
        f"y vino {type(raw).__name__}; se conserva en extra.{KEY_CREATOR}_raw"
    )
    return None


# ------------------------------------------------------------------ documentos


def _docs(
    raw: Any,  # noqa: ANN401 - valor libre del export
    project_id: str,
    file: SourceFile,
    report: Report,
) -> list[ProjectDoc]:
    """CA-3: un `ProjectDoc` por entrada, con el contenido marcado como no disponible."""
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        report.add_error(
            CATEGORY,
            f"se esperaba un array y vino {type(raw).__name__}",
            item_id=f"{project_id}/{KEY_DOCS}",
            source_file=file.path,
        )
        return []
    docs = [_doc(entry, project_id, index, file, report) for index, entry in enumerate(raw)]
    return [doc for doc in docs if doc is not None]


def _doc(
    raw: Any,  # noqa: ANN401 - valor libre del export
    project_id: str,
    index: int,
    file: SourceFile,
    report: Report,
) -> ProjectDoc | None:
    """Una entrada de `docs[]` → `ProjectDoc`, o `None` si no tenía forma de objeto."""
    item_id = f"{project_id}/{KEY_DOCS}[{index}]"
    if not isinstance(raw, Mapping):
        report.add_error(
            CATEGORY,
            f"se esperaba un objeto y vino {type(raw).__name__}",
            item_id=item_id,
            source_file=file.path,
        )
        return None
    values = {str(key): value for key, value in raw.items() if key not in _DOC_KEYS}
    doc_id = _doc_id(raw.get(KEY_UUID), project_id, index, file, report, values)
    values.update(
        id=doc_id,
        filename=_text(raw.get(KEY_FILENAME)),
        created_at=raw.get(KEY_CREATED_AT),
        # CA-3: que falte el contenido lo cuenta `parse()`, cuando ya se sabe qué
        # proyectos sobrevivieron al dedupe.
        content=_content(raw.get(KEY_CONTENT), item_id, file, report, values),
    )
    return ProjectDoc.model_validate(values)


def _doc_id(
    raw: Any,  # noqa: ANN401 - valor libre del export
    project_id: str,
    index: int,
    file: SourceFile,
    report: Report,
    extra: dict[str, Any],
) -> str:
    """Identificador del doc; si el export no lo trae se da uno sintético y se avisa.

    Descartar el documento por un `uuid` ausente perdería su `filename`, que es lo único
    legible que el export trae de él (mismo criterio que un mensaje sin `uuid` en
    `conversations`). El identificador sintético es determinista: misma entrada, mismo id.
    """
    if isinstance(raw, str) and raw.strip():
        return raw
    item = f"{KEY_DOCS}[{index}]"
    synthetic = f"{project_id}#{item}"
    extra[SYNTHETIC_ID_KEY] = True
    report.add_warning(
        DOC_WITHOUT_ID_WARNING.format(file=file.path, item=item, project=project_id, doc=synthetic)
    )
    return synthetic


def _content(
    raw: Any,  # noqa: ANN401 - valor libre del export
    item_id: str,
    file: SourceFile,
    report: Report,
    extra: dict[str, Any],
) -> str | None:
    """CA-3: `None` mientras el export no traiga el texto; si lo trae, tal cual."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    extra[f"{KEY_CONTENT}_raw"] = raw
    report.add_warning(
        f"{file.path}: `{KEY_CONTENT}` de {item_id} debería ser texto y vino "
        f"{type(raw).__name__}; se conserva en extra.{KEY_CONTENT}_raw"
    )
    return None


__all__ = [
    "CATEGORY",
    "DOCS_WITHOUT_CONTENT_WARNING",
    "DOC_WITHOUT_ID_WARNING",
    "MAX_JSON_BYTES",
    "parse",
    "parse_sorted",
    "sort_key",
]
