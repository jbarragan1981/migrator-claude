"""Parser de `frames` (spec 03, sección `frames`).

Lo que confirmó la Fase 0 (`docs/export-format/frames.md`) y deja de ser "desconocido":
`frames` son **artefactos**, un archivo JSON por artefacto en
`frames-000/artifacts/<uuid>/*.json` (17 archivos y ~11 KB en el export observado). Cada
archivo es un objeto con `id`, `kind`, `visibility`, `owner_account`, `updated_at`,
`active_version` y `versions[]` (de 1 a 3 ítems observados, cada uno con `id`, `title`,
`description` y `created_at`).

Decisiones de este módulo:

* **El contenido real no viaja (CA-2)** — ninguno de los campos observados trae el
  código, el documento o la imagen que el usuario vio en Claude.ai, y todavía no se sabe
  dónde vive (`docs/export-format/frames.md`, sección Dudas). Mismo criterio que
  `projects.docs[]`: `Frame.payload` conserva el JSON **completo tal cual** para no
  perder nada el día que se descubra, y el render lo DICE con todas las letras
  (`FRAME_CONTENT_UNAVAILABLE` en `rendering/render.py`). Nunca se inventa contenido ni
  se deja un bloque vacío en silencio (CLAUDE.md §1.3): en `report.warnings` queda UNA
  advertencia agregada por corrida (`{frames} llegan solo con su metadata`), no una por
  artefacto — 17 líneas idénticas tapaban en el resumen del CLI a las advertencias
  accionables, mismo criterio que `ORPHAN_PROJECTS_WARNING` en `usecases/links.py`. Se
  cuenta en `parse()`, después del dedupe, para no hablar de archivos que no se escriben.
* **`payload` y `extra` no se pisan** — `payload` es el JSON íntegro (incluidos los campos
  que la entidad sí mapea); `extra` son solo los campos que no reconocemos, que son los
  que el frontmatter publica bajo `extra:` (CA-C4). Aquí sí se puede duplicar, al revés
  que en `conversations`: los 17 archivos reales suman 11 KB, no 98 MB.
* **Versión activa (CA-3)** — `active_version` se compara con los `versions[].id`. Que no
  coincida con ninguna es una ADVERTENCIA, no una excepción: el artefacto se emite igual,
  con `active_version` tal cual vino, y `Frame.active()` devuelve `None`. Si
  `active_version` llegara con otra forma (no texto) no se fuerza el tipo: queda en
  `extra["active_version_raw"]` con aviso, igual que `creator` en `projects`.
* **Versión sin `id`** — no se descarta: perder su `title` y su `description`, que es lo
  único legible que el export trae de ella, sería peor. Recibe el id sintético y
  determinista `<id del artefacto>#versions[<posición>]`, se marca con
  `extra["synthetic_id"]` y se avisa. Mismo criterio que un doc sin `uuid` en `projects`.
  El identificador del ARTEFACTO sí es obligatorio.
* **Raíz que es un array** — se lee como varios artefactos con una advertencia, para no
  devolver cero en silencio (la simétrica de la tolerancia de `projects`).
* **`json.load` con techo** — mismo criterio que `memories`, `light_metadata` y
  `projects`: aquí cada archivo pesa menos de 1 KB. La regla de streaming (CA-C3) apunta a
  `conversations.json`; aun así se comprueba el tamaño antes de leer.
* **Orden canónico (CA-C5)** — el artefacto NO tiene `created_at` propio: la única fecha
  de primer nivel es `updated_at`, y `created_at` solo existe dentro de cada versión. El
  orden canónico de la colección es por `updated_at` y luego por `id`, en vez de por una
  fecha derivada de `versions[]`, para que dependa de un dato que el export sí trae del
  artefacto. La fecha de creación derivada (la de la versión más antigua) la calcula el
  render para el frontmatter, donde el campo es obligatorio.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from claude_export_md.domain.entities import Frame, FrameVersion, Report
from claude_export_md.errors import CorruptFileError
from claude_export_md.ports.source import JSON, ExportSource, SourceFile

logger = logging.getLogger(__name__)

#: Nombre de la categoría tal como la nombran el manifiesto y `ExportSource`.
CATEGORY = "frames"

#: Techo para leer un archivo entero (CA-C3). Por encima se registra y no se carga.
MAX_JSON_BYTES = 10 * 1024 * 1024

#: Claves del archivo de un artefacto que el parser mapea a un campo de `Frame`.
KEY_ID = "id"
KEY_KIND = "kind"
KEY_VISIBILITY = "visibility"
KEY_OWNER = "owner_account"
KEY_UPDATED_AT = "updated_at"
KEY_ACTIVE_VERSION = "active_version"
KEY_VERSIONS = "versions"
_FRAME_KEYS = frozenset(
    {
        KEY_ID,
        KEY_KIND,
        KEY_VISIBILITY,
        KEY_OWNER,
        KEY_UPDATED_AT,
        KEY_ACTIVE_VERSION,
        KEY_VERSIONS,
    }
)

#: Claves de una entrada de `versions[]` que el parser mapea a un campo de `FrameVersion`.
KEY_TITLE = "title"
KEY_DESCRIPTION = "description"
KEY_CREATED_AT = "created_at"
_VERSION_KEYS = frozenset({KEY_ID, KEY_TITLE, KEY_DESCRIPTION, KEY_CREATED_AT})

#: Prefijo con el que se identifica un ítem cuando la raíz es un array (tolerancia).
ITEM_PREFIX = "item"
#: Campo de `extra` que anota de qué archivo del export salió el artefacto (spec 04).
SOURCE_FILE_KEY = "source_file"
#: Marca de una versión a la que hubo que darle un identificador (ver `_version`).
SYNTHETIC_ID_KEY = "synthetic_id"

#: Advertencia de CA-2, UNA por corrida: el export no trae el contenido de los artefactos.
#: `{frames}` llega ya pluralizado (`1 artefacto` / `17 artefactos`).
FRAMES_WITHOUT_CONTENT_WARNING = (
    "{frames} {verb} solo con su metadata (versiones, títulos, descripciones y fechas); "
    "el contenido no está en este export (cada artefacto lo dice en su propio archivo)"
)
#: Advertencia de CA-3: `active_version` no coincide con ninguna versión.
ACTIVE_VERSION_NOT_FOUND_WARNING = (
    "{file}: `active_version` {active} del artefacto {frame} no coincide con ningún "
    "`id` de versions[]; se conserva tal cual y no se marca ninguna versión activa"
)
#: Advertencia de una versión sin `id` propio (ver `_version`).
VERSION_WITHOUT_ID_WARNING = (
    "{file}: la versión {item} del artefacto {frame} no trae `id`; "
    "se le da el identificador sintético {version}"
)

#: Fecha de relleno para ordenar: solo se usa como desempate, nunca se escribe.
_NO_DATE = datetime.min.replace(tzinfo=UTC)


def parse(source: ExportSource, report: Report) -> Iterator[Frame]:
    """Artefactos del export, un archivo cada uno y sin repetir `id` (CA-1, CA-C1).

    No lanza: un archivo ilegible o un ítem con forma inesperada se acumula en
    `report.errors` y el resto sigue (CA-C2).

    La advertencia de CA-2 se cuenta aquí, sobre los artefactos que de verdad se emiten, y
    se escribe una sola vez al terminar: dentro de `_frame` avisaba también por el
    artefacto repetido que el dedupe descartaba después, y el informe hablaba de archivos
    que nunca se escribieron.
    """
    seen: set[str] = set()
    without_content = 0
    for file in _files(source, report):
        data = _load(source, file, report)
        if data is None:
            continue
        for item_id, raw in _items(data, file, report):
            frame = _frame(raw, item_id, file, report)
            if frame is None:
                continue
            if frame.id in seen:
                report.add_warning(
                    f"{file.path}: artefacto repetido {frame.id}; se conserva el primero"
                )
                continue
            seen.add(frame.id)
            report.count(CATEGORY)
            without_content += 1
            yield frame
    if without_content:
        report.add_warning(
            FRAMES_WITHOUT_CONTENT_WARNING.format(
                frames=_plural(without_content, "artefacto", "artefactos"),
                verb="llega" if without_content == 1 else "llegan",
            )
        )


def _plural(count: int, singular: str, plural: str) -> str:
    """`1 artefacto` / `17 artefactos` (mismo criterio que el resumen del CLI)."""
    return f"{count} {singular if count == 1 else plural}"


def parse_sorted(source: ExportSource, report: Report) -> list[Frame]:
    """Los mismos artefactos ya ordenados por `updated_at` y luego `id` (CA-C5).

    `parse` emite en el orden de los archivos, que ya es determinista; este es el orden
    canónico de la colección, el que necesita el `_index.md`. Los artefactos sin fecha van
    al final (no se les inventa una), ordenados entre sí por `id`.
    """
    return sorted(parse(source, report), key=sort_key)


def sort_key(frame: Frame) -> tuple[bool, datetime, str]:
    """Clave de orden canónico de un artefacto (CA-C5).

    Se usa `updated_at` y no una fecha derivada de `versions[]`: es la única fecha que el
    export trae del artefacto en sí (ver las decisiones del módulo).
    """
    updated = frame.updated_at
    return (updated is None, updated or _NO_DATE, frame.id)


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
        logger.warning("Artefacto ilegible en %s: %s", file.path, exc)
        report.add_error(CATEGORY, f"JSON ilegible: {exc}", source_file=file.path)
        return None


def _items(data: Any, file: SourceFile, report: Report) -> list[tuple[str | None, Any]]:  # noqa: ANN401
    """Los artefactos del archivo: el objeto (CA-1) o los ítems del array (tolerancia).

    El `item_id` es `None` cuando el archivo ES el artefacto: ahí el que identifica al
    ítem en `Report` es el propio `source_file`, y un `item[0]` solo sería ruido.
    """
    if isinstance(data, Mapping):
        return [(None, data)]
    if isinstance(data, Sequence) and not isinstance(data, str | bytes):
        report.add_warning(
            f"{file.path}: la raíz del JSON es un array y se esperaba un artefacto por "
            "archivo; se leen todos sus ítems como artefactos"
        )
        return [(f"{ITEM_PREFIX}[{index}]", raw) for index, raw in enumerate(data)]
    report.add_error(
        CATEGORY,
        f"la raíz del JSON es {type(data).__name__}, se esperaba un objeto con el artefacto",
        source_file=file.path,
    )
    return []


# ------------------------------------------------------------------ artefacto


def _frame(
    raw: Any,  # noqa: ANN401 - lo que venga en el archivo del export
    item_id: str | None,
    file: SourceFile,
    report: Report,
) -> Frame | None:
    """El objeto del archivo → `Frame`, o `None` si no se pudo identificar (CA-C2)."""
    if not isinstance(raw, Mapping):
        report.add_error(
            CATEGORY,
            f"se esperaba un objeto y vino {type(raw).__name__}",
            item_id=item_id,
            source_file=file.path,
        )
        return None
    frame_id = raw.get(KEY_ID)
    if not isinstance(frame_id, str) or not frame_id.strip():
        report.add_error(
            CATEGORY,
            "artefacto sin `id`: no se puede identificar",
            item_id=item_id,
            source_file=file.path,
        )
        return None
    values = {str(key): value for key, value in raw.items() if key not in _FRAME_KEYS}
    versions = _versions(raw.get(KEY_VERSIONS), frame_id, file, report)
    active = _active_version(raw.get(KEY_ACTIVE_VERSION), frame_id, file, report, values)
    _check_active_version(active, versions, frame_id, file, report)
    values.update(
        id=frame_id,
        kind=_text(raw.get(KEY_KIND)),
        visibility=_text(raw.get(KEY_VISIBILITY)),
        owner_account=_text(raw.get(KEY_OWNER)),
        updated_at=raw.get(KEY_UPDATED_AT),
        active_version=active,
        versions=versions,
        # CA-2: el JSON entero, tal cual, mientras no se sepa dónde vive el contenido.
        payload={str(key): value for key, value in raw.items()},
    )
    values.setdefault(SOURCE_FILE_KEY, file.path)
    # CA-2: que el contenido no venga lo cuenta `parse()`, cuando ya se sabe qué
    # artefactos sobrevivieron al dedupe.
    return Frame.model_validate(values)


def _text(value: Any) -> str | None:  # noqa: ANN401 - valor libre del export
    """Solo se acepta texto; cualquier otra forma deja el campo vacío, no el artefacto."""
    return value if isinstance(value, str) else None


def _active_version(
    raw: Any,  # noqa: ANN401 - valor libre del export
    frame_id: str,
    file: SourceFile,
    report: Report,
    extra: dict[str, Any],
) -> str | None:
    """CA-3: `active_version` es un identificador de versión; con otra forma se conserva."""
    if raw is None or isinstance(raw, str):
        return raw
    extra[f"{KEY_ACTIVE_VERSION}_raw"] = raw
    report.add_warning(
        f"{file.path}: `{KEY_ACTIVE_VERSION}` del artefacto {frame_id} debería ser texto "
        f"y vino {type(raw).__name__}; se conserva en extra.{KEY_ACTIVE_VERSION}_raw"
    )
    return None


def _check_active_version(
    active: str | None,
    versions: Sequence[FrameVersion],
    frame_id: str,
    file: SourceFile,
    report: Report,
) -> None:
    """CA-3: que `active_version` no coincida con ninguna versión se avisa, no se lanza."""
    if active is None or any(version.id == active for version in versions):
        return
    report.add_warning(
        ACTIVE_VERSION_NOT_FOUND_WARNING.format(file=file.path, active=active, frame=frame_id)
    )


# -------------------------------------------------------------------- versiones


def _versions(
    raw: Any,  # noqa: ANN401 - valor libre del export
    frame_id: str,
    file: SourceFile,
    report: Report,
) -> list[FrameVersion]:
    """CA-3: una `FrameVersion` por entrada, en el orden del export (1 a 3 observadas)."""
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        report.add_error(
            CATEGORY,
            f"se esperaba un array y vino {type(raw).__name__}",
            item_id=f"{frame_id}/{KEY_VERSIONS}",
            source_file=file.path,
        )
        return []
    versions = [_version(entry, frame_id, index, file, report) for index, entry in enumerate(raw)]
    return [version for version in versions if version is not None]


def _version(
    raw: Any,  # noqa: ANN401 - valor libre del export
    frame_id: str,
    index: int,
    file: SourceFile,
    report: Report,
) -> FrameVersion | None:
    """Una entrada de `versions[]` → `FrameVersion`, o `None` si no era un objeto."""
    if not isinstance(raw, Mapping):
        report.add_error(
            CATEGORY,
            f"se esperaba un objeto y vino {type(raw).__name__}",
            item_id=f"{frame_id}/{KEY_VERSIONS}[{index}]",
            source_file=file.path,
        )
        return None
    values = {str(key): value for key, value in raw.items() if key not in _VERSION_KEYS}
    values.update(
        id=_version_id(raw.get(KEY_ID), frame_id, index, file, report, values),
        title=_text(raw.get(KEY_TITLE)),
        description=_text(raw.get(KEY_DESCRIPTION)),
        created_at=raw.get(KEY_CREATED_AT),
    )
    return FrameVersion.model_validate(values)


def _version_id(
    raw: Any,  # noqa: ANN401 - valor libre del export
    frame_id: str,
    index: int,
    file: SourceFile,
    report: Report,
    extra: dict[str, Any],
) -> str:
    """Identificador de la versión; si el export no lo trae se da uno sintético y se avisa.

    Descartar la versión por un `id` ausente perdería su título y su descripción, que es
    lo único legible que el export trae de ella (mismo criterio que un doc sin `uuid` en
    `projects`). El identificador sintético es determinista: misma entrada, mismo id.
    """
    if isinstance(raw, str) and raw.strip():
        return raw
    item = f"{KEY_VERSIONS}[{index}]"
    synthetic = f"{frame_id}#{item}"
    extra[SYNTHETIC_ID_KEY] = True
    report.add_warning(
        VERSION_WITHOUT_ID_WARNING.format(
            file=file.path, item=item, frame=frame_id, version=synthetic
        )
    )
    return synthetic


__all__ = [
    "ACTIVE_VERSION_NOT_FOUND_WARNING",
    "CATEGORY",
    "FRAMES_WITHOUT_CONTENT_WARNING",
    "MAX_JSON_BYTES",
    "VERSION_WITHOUT_ID_WARNING",
    "parse",
    "parse_sorted",
    "sort_key",
]
