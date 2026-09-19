"""Render de entidades a Markdown con Jinja2 (spec 04).

Módulo puro: construye texto, no escribe nada (eso es `adapters/sink_filesystem.py`) y
no mira el reloj (spec 04 CA-10). Las plantillas por defecto viven en `templates/` y el
usuario puede sustituirlas una a una con `--templates ./mis-plantillas` (CA-9).

Decisiones propias de `Memory`, que el export no trae resueltas:

* **Título** — una memoria no tiene `title` en el export. Se usa el último segmento de
  `Memory.path` sin la extensión (`/people/Ana María.md` → `Ana María`), que es el único
  texto legible que trae el origen y además es estable. Las dos memorias de ruta
  sintética (ADR-0005) no tienen ningún texto que usar, así que llevan un título fijo
  que dice qué son (`Memoria de conversaciones`, `Memoria del proyecto <uuid>`).
* **Nombre del archivo** — la ruta de salida conserva la jerarquía de `Memory.path` con
  cada segmento slugificado (`/people/Ana María.md` → `memories/people/ana-maria.md`),
  porque `Memory.path` viene del export y no tiene por qué ser un nombre de archivo
  válido. Si dos rutas distintas slugifican igual, AMBAS reciben el hash corto de su
  ruta original: así el desempate no depende del orden en que se rendericen.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined

from claude_export_md.domain.entities import (
    CONVERSATIONS_MEMORY_PATH,
    ORIGIN_CONVERSATIONS_MEMORY,
    ORIGIN_MEMORY_FILES,
    Memory,
)
from claude_export_md.rendering.filters import (
    code_fence,
    hhmm,
    iso_utc,
    jsonable,
    md_cell,
    short_hash,
    slugify,
    yaml_block,
    yaml_inline,
    yaml_value,
)

logger = logging.getLogger(__name__)

#: Carpeta de las plantillas que trae la librería.
TEMPLATES_DIR = Path(__file__).parent / "templates"

#: Filtros que ve CUALQUIER plantilla, incluidas las del usuario (`--templates`).
#: Esta tabla y la de `docs/specs/04-markdown-output.md` §Plantillas son el mismo
#: contrato: con `StrictUndefined`, un filtro documentado y no registrado aquí hace
#: reventar la plantilla del usuario con `TemplateAssertionError`.
FILTERS = {
    "code_fence": code_fence,
    "hhmm": hhmm,
    "iso_utc": iso_utc,
    "md_cell": md_cell,
    "slugify": slugify,
    "yaml_block": yaml_block,
    "yaml_inline": yaml_inline,
    "yaml_value": yaml_value,
}

#: Plantilla y `type` de frontmatter de una memoria.
MEMORY_TEMPLATE = "memory.md.j2"
TYPE_MEMORY = "memory"

#: Carpeta de las memorias dentro de la salida (CLAUDE.md §5).
MEMORIES_DIR = "memories"
#: Extensión de todo lo que genera la herramienta.
MARKDOWN_SUFFIX = ".md"
#: Extensiones que se quitan del último segmento antes de slugificarlo.
TEXT_SUFFIXES = frozenset({".md", ".markdown", ".txt"})

#: Títulos de las memorias que no tienen ningún texto propio (ADR-0005).
CONVERSATIONS_MEMORY_TITLE = "Memoria de conversaciones"
PROJECT_MEMORY_TITLE = "Memoria del proyecto"

#: Etiqueta común a todas las memorias, más la del origen y la carpeta de la ruta.
TAG_MEMORY = "memory"
TAG_PROJECT = "project"

#: Campo de `extra` que pone el parser y que en el frontmatter va al primer nivel.
SOURCE_FILE_KEY = "source_file"
ORIGIN_KEY = "origin"


# ------------------------------------------------------------------- entorno


def build_environment(user_templates: Path | str | None = None) -> Environment:
    """Entorno de Jinja2 con los filtros propios y, si se pasa, las plantillas del usuario.

    `autoescape` queda apagado a propósito: la salida es Markdown, no HTML, y escapar
    sería corromper el texto del usuario (skill `markdown-template`, regla 5).
    `StrictUndefined` hace que una plantilla propia que use una variable inexistente
    falle en vez de escribir un hueco silencioso.
    """
    loaders: list[FileSystemLoader] = []
    if user_templates is not None:
        loaders.append(FileSystemLoader(str(user_templates)))
    loaders.append(FileSystemLoader(str(TEMPLATES_DIR)))
    environment = Environment(
        loader=ChoiceLoader(loaders),
        autoescape=False,  # noqa: S701 - Markdown, no HTML
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    environment.filters.update(FILTERS)
    return environment


# ------------------------------------------------------------------ memorias


def _origin(memory: Memory) -> str | None:
    value = (memory.model_extra or {}).get(ORIGIN_KEY)
    return value if isinstance(value, str) else None


def _last_segment(path: str) -> str:
    """Último tramo de la ruta sin la extensión de texto: `/people/Ana.md` → `Ana`."""
    name = PurePosixPath(path).name
    if PurePosixPath(name).suffix.lower() in TEXT_SUFFIXES:
        return PurePosixPath(name).stem
    return name


def memory_title(memory: Memory) -> str:
    """Título legible de una memoria; ver la nota de decisiones del módulo."""
    if _origin(memory) == ORIGIN_CONVERSATIONS_MEMORY or memory.path == CONVERSATIONS_MEMORY_PATH:
        return CONVERSATIONS_MEMORY_TITLE
    if memory.project_id:
        return f"{PROJECT_MEMORY_TITLE} {memory.project_id}"
    return _last_segment(memory.path) or memory.path


def memory_tags(memory: Memory) -> list[str]:
    """Etiquetas del frontmatter: siempre `memory`, más el origen y la carpeta."""
    tags = [TAG_MEMORY]
    origin = _origin(memory)
    if origin:
        tags.append(slugify(origin))
    if memory.project_id:
        tags.append(TAG_PROJECT)
    if origin in (None, ORIGIN_MEMORY_FILES):
        # Solo las rutas reales tienen carpetas con significado para el usuario;
        # las sintéticas (`_project_memories`) son nuestras, no del export.
        tags.extend(slugify(part) for part in PurePosixPath(memory.path).parts[:-1] if part != "/")
    return list(dict.fromkeys(tag for tag in tags if tag))


def memory_output_path(memory: Memory) -> str:
    """Ruta del `.md` relativa a la raíz de la salida, sin resolver colisiones."""
    parts = [part for part in memory.path.split("/") if part]
    folders = [slugify(part) for part in parts[:-1]]
    name = slugify(_last_segment(memory.path)) if parts else slugify("")
    return "/".join([MEMORIES_DIR, *folders, name + MARKDOWN_SUFFIX])


def assign_output_paths(memories: Sequence[Memory]) -> list[tuple[Memory, str]]:
    """Ruta de salida definitiva de cada memoria, con las colisiones ya desempatadas.

    Dos `Memory.path` distintos pueden slugificar igual (`/people/Ana María.md` y
    `/people/ana-maria!.md`). En ese caso las dos llevan el hash corto de su ruta
    original, de forma que el nombre de cada archivo depende solo de su propia ruta y no
    del orden de la colección (spec 04 CA-1).
    """
    assigned = [(memory, memory_output_path(memory)) for memory in memories]
    repeated = {path for path, times in Counter(path for _, path in assigned).items() if times > 1}
    return [
        (memory, _disambiguate(memory, path) if path in repeated else path)
        for memory, path in assigned
    ]


def _disambiguate(memory: Memory, path: str) -> str:
    return f"{path.removesuffix(MARKDOWN_SUFFIX)}-{short_hash(memory.path)}{MARKDOWN_SUFFIX}"


def memory_context(memory: Memory) -> dict[str, Any]:
    """Variables que ve `memory.md.j2` (documentadas en la propia plantilla)."""
    extra = dict(memory.model_extra or {})
    source_file = extra.pop(SOURCE_FILE_KEY, None)
    return {
        "memory": memory,
        "id": memory.path,
        "type": TYPE_MEMORY,
        "title": memory_title(memory),
        # El export no trae fecha de creación de una memoria; el campo es obligatorio
        # en el frontmatter (spec 04) y se emite en null antes que inventarlo.
        "created_at": None,
        "updated_at": iso_utc(memory.updated_at),
        "source_file": source_file,
        "project_id": memory.project_id,
        "tags": memory_tags(memory),
        "extra": jsonable(extra),
        "content": memory.content,
    }


def render_memory(memory: Memory, environment: Environment | None = None) -> str:
    """Markdown completo de una memoria: frontmatter + su contenido tal cual."""
    env = environment if environment is not None else build_environment()
    rendered = env.get_template(MEMORY_TEMPLATE).render(**memory_context(memory))
    return rendered.rstrip("\n") + "\n"


def render_memories(
    memories: Iterable[Memory], environment: Environment | None = None
) -> list[tuple[str, str]]:
    """`(ruta relativa, markdown)` de cada memoria, lista para escribir."""
    env = environment if environment is not None else build_environment()
    return [
        (path, render_memory(memory, env)) for memory, path in assign_output_paths(list(memories))
    ]


__all__ = [
    "CONVERSATIONS_MEMORY_TITLE",
    "MEMORIES_DIR",
    "MEMORY_TEMPLATE",
    "PROJECT_MEMORY_TITLE",
    "TEMPLATES_DIR",
    "TYPE_MEMORY",
    "assign_output_paths",
    "build_environment",
    "memory_context",
    "memory_output_path",
    "memory_tags",
    "memory_title",
    "render_memories",
    "render_memory",
]
