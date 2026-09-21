"""Filtros de plantilla y ayudas de formato (spec 04).

Todo lo de aquí es puro y determinista: mismas entradas → mismas salidas, sin reloj y
sin sistema de archivos. Son las piezas que comparten todas las plantillas Markdown
(`slugify` para nombres de archivo, `iso_utc` para fechas, los tres `yaml_*` para
emitir frontmatter que sea YAML válido con cualquier contenido del usuario).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import yaml

#: Largo máximo del slug de un nombre de archivo (skill `markdown-template`, regla 3).
SLUG_MAX_LENGTH = 60
#: Slug de emergencia cuando el texto no deja ni un carácter ASCII (p. ej. "日本語").
SLUG_FALLBACK = "sin-titulo"
#: Longitud del hash con el que se desempatan dos slugs iguales.
SHORT_HASH_LENGTH = 8

#: Formato de fecha del frontmatter: ISO-8601 UTC sin microsegundos.
ISO_UTC = "%Y-%m-%dT%H:%M:%SZ"
#: Formato de la hora que acompaña a cada turno de una conversación (spec 04 CA-3).
HOUR_MINUTE = "%H:%M"

#: Cerca de código por defecto y mínimo de caracteres de una cerca.
FENCE_CHAR = "`"
FENCE_MIN = 3

#: Lo que se ve en una celda de tabla que no tiene valor (spec 04 CA-7).
EMPTY_CELL = "—"
#: Caracteres que romperían una tabla o un enlace Markdown desde dentro de una celda.
_CELL_ESCAPES = str.maketrans({"\\": "\\\\", "|": "\\|", "[": "\\[", "]": "\\]"})
_WHITESPACE_RUN = re.compile(r"\s+")

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
#: Clave descartable para reutilizar el dumper de YAML sobre un valor suelto.
_KEY = "v"
#: Ancho "infinito": el dumper no debe partir un título largo en varias líneas.
_WIDTH = 1_000_000
#: Marcador de fin de documento que PyYAML añade tras un escalar suelto.
_DOC_END = "\n..."


def slugify(value: str, max_length: int = SLUG_MAX_LENGTH) -> str:
    """`"Análisis Ñandú / Q3"` → `"analisis-nandu-q3"` (spec 04 CA-6).

    ASCII en minúsculas, separadores colapsados a un guion y recorte por palabra
    entera. Nunca devuelve cadena vacía: un texto sin ningún carácter ASCII produce
    `SLUG_FALLBACK`, porque el resultado va a ser un nombre de archivo.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii").lower()
    slug = _NON_ALNUM.sub("-", ascii_only).strip("-")
    if len(slug) > max_length:
        slug = _cut(slug, max_length)
    return slug or SLUG_FALLBACK


def _cut(slug: str, max_length: int) -> str:
    """Recorta sin partir una palabra, salvo que la primera ya sea más larga que el tope."""
    head, separator, _tail = slug[:max_length].rpartition("-")
    if separator and len(head) >= max_length // 2:
        return head.strip("-")
    return slug[:max_length].strip("-")


def short_hash(value: str, length: int = SHORT_HASH_LENGTH) -> str:
    """Huella corta y estable de un texto, para desempatar nombres de archivo."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def iso_utc(value: datetime | None) -> str | None:
    """`datetime` → `"2026-09-18T16:59:47Z"`; `None` se propaga tal cual.

    Se descartan los microsegundos: el export los trae, pero en el frontmatter no
    aportan nada y ensucian los diffs entre corridas de versiones distintas.
    """
    if value is None:
        return None
    return value.astimezone(UTC).strftime(ISO_UTC)


def hhmm(value: datetime | None) -> str | None:
    """`datetime` → `"14:32"` en UTC; `None` se propaga tal cual (spec 04 CA-3)."""
    if value is None:
        return None
    return value.astimezone(UTC).strftime(HOUR_MINUTE)


def code_fence(text: str, language: str = "") -> str:
    """Envuelve un texto en una cerca de código más larga que cualquiera que traiga dentro.

    Sin esto, un resultado de herramienta que ya contenga ``` cerraría la cerca antes de
    tiempo y rompería el Markdown de alrededor (spec 04 CA-4).
    """
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = FENCE_CHAR * max(FENCE_MIN, longest + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def md_cell(value: Any) -> str:  # noqa: ANN401 - acepta cualquier valor del export
    """Un valor dentro de una celda de tabla Markdown, sin que pueda partir la fila.

    El título de una conversación es texto libre del usuario: un `|` añadiría una
    columna, un salto de línea cortaría la tabla y un `[`/`]` rompería el enlace que la
    celda envuelve (spec 04 CA-7). `None` y el texto vacío se ven como `EMPTY_CELL`.
    """
    if value is None:
        return EMPTY_CELL
    text = _WHITESPACE_RUN.sub(" ", str(value)).strip()
    return text.translate(_CELL_ESCAPES) if text else EMPTY_CELL


def jsonable(value: Any) -> Any:  # noqa: ANN401 - acepta cualquier valor del export
    """Convierte fechas a ISO-8601 UTC recursivamente para que YAML las emita como texto."""
    if isinstance(value, datetime):
        return iso_utc(value)
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(item) for item in value]
    return value


def yaml_value(value: Any) -> str:  # noqa: ANN401 - acepta cualquier valor del export
    """Serializa un valor suelto para ponerlo detrás de `clave: ` en el frontmatter.

    Se apoya en el dumper de PyYAML (no en comillas puestas a mano) para que un título
    con `:`, comillas o saltos de línea siga produciendo YAML válido; un texto
    multilínea sale como bloque `|-` ya indentado.
    """
    dumped = yaml.safe_dump(
        {_KEY: jsonable(value)},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
        width=_WIDTH,
    )
    return dumped[len(_KEY) + 1 :].strip("\n").lstrip(" ")


def yaml_inline(value: Any) -> str:  # noqa: ANN401 - acepta cualquier valor del export
    """Igual que `yaml_value` pero en estilo de flujo: `[memory, memory-files]`.

    Es lo que se quiere para las listas cortas del frontmatter (`tags`), que en estilo
    de bloque ocuparían una línea por elemento.
    """
    dumped = yaml.safe_dump(
        jsonable(value),
        allow_unicode=True,
        default_flow_style=True,
        sort_keys=True,
        width=_WIDTH,
    ).strip("\n")
    # Un escalar suelto sale como documento propio y arrastra el marcador de fin.
    return dumped[: -len(_DOC_END)] if dumped.endswith(_DOC_END) else dumped


def yaml_block(value: Any, indent: int = 2) -> str:  # noqa: ANN401 - valor del export
    """Serializa un mapa como bloque indentado, para colgarlo de `extra:`."""
    dumped = yaml.safe_dump(
        jsonable(value),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
        width=_WIDTH,
    ).rstrip("\n")
    padding = " " * indent
    return "\n".join(padding + line if line else line for line in dumped.split("\n"))


__all__ = [
    "EMPTY_CELL",
    "HOUR_MINUTE",
    "ISO_UTC",
    "SHORT_HASH_LENGTH",
    "SLUG_FALLBACK",
    "SLUG_MAX_LENGTH",
    "code_fence",
    "hhmm",
    "iso_utc",
    "jsonable",
    "md_cell",
    "short_hash",
    "slugify",
    "yaml_block",
    "yaml_inline",
    "yaml_value",
]
