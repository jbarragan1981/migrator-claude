"""Índice global (`_index.md`) y portada (`README.md`) de la salida.

Módulo puro, como el resto de `rendering/`: arma texto a partir de lo que ya se
convirtió y no escribe nada ni mira el reloj. La única fecha que puede aparecer aquí es
la del MANIFIESTO del export (cuándo lo generó Anthropic), nunca la de la corrida
(CLAUDE.md §1.4).

Decisiones:

* **Qué lleva el índice** — spec 04 CA-7 solo exige la tabla de conversaciones (fecha
  descendente, enlace relativo, proyecto y nº de mensajes). Se añade una segunda tabla
  con las memorias porque son la mitad de lo que M1 escribe y un índice que no las
  nombre dejaría media salida sin puerta de entrada; van en su propia sección, así que
  una plantilla propia puede quitarla sin tocar la de conversaciones.
* **Proyecto** — hasta que exista el parser de `projects` (M2) no hay nombre de
  proyecto que mostrar: se imprime el `project_uuid` crudo, que es lo que trae el
  export, en vez de dejar la columna vacía.
* **Orden** — fecha descendente y, a igualdad, `id` ascendente. Lo que no tiene fecha va
  al final (no se le inventa una) y también se ordena por `id`, para que dos corridas
  produzcan exactamente el mismo archivo.
* **Celdas** — el título es texto libre del usuario: se escapa con el filtro `md_cell`,
  porque un `|` o un salto de línea partirían la tabla.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from jinja2 import Environment

from claude_export_md.domain.entities import Conversation, Memory
from claude_export_md.rendering.conversations import (
    conversation_date,
    conversation_output_path,
    conversation_title,
)
from claude_export_md.rendering.render import build_environment, memory_title

#: Plantillas y nombres de archivo de la raíz de la salida (CLAUDE.md §5).
INDEX_TEMPLATE = "index.md.j2"
README_TEMPLATE = "readme.md.j2"
INDEX_NAME = "_index.md"
README_NAME = "README.md"

#: Carpeta y archivos del informe de la corrida (CLAUDE.md §5, spec 04 CA-8). Viven
#: aquí, con los demás nombres del árbol de salida, y no en el sink: son el contrato
#: de la salida, no una decisión del destino que la escribe (ADR-0006).
REPORT_DIR = "_report"
SUMMARY_NAME = "summary.json"
ERRORS_NAME = "errors.jsonl"
INVENTORY_NAME = "inventory.json"
ERRORS_PATH = f"{REPORT_DIR}/{ERRORS_NAME}"
SUMMARY_PATH = f"{REPORT_DIR}/{SUMMARY_NAME}"
INVENTORY_PATH = f"{REPORT_DIR}/{INVENTORY_NAME}"

#: Formato de la columna de fecha de las tablas.
DAY = "%Y-%m-%d"

#: Fecha con la que se ordena lo que no tiene ninguna (va al final, ver módulo).
_NO_DATE = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class IndexEntry:
    """Una fila del índice.

    Es deliberadamente diminuta: `convert` la va acumulando mientras escribe en
    streaming, de modo que en memoria queden las ~291 filas del índice y no las ~291
    conversaciones enteras.
    """

    id: str
    title: str
    path: str
    date: datetime | None = None
    project_id: str | None = None
    message_count: int | None = None


def conversation_entry(conversation: Conversation, path: str | None = None) -> IndexEntry:
    """Fila del índice de una conversación, con la misma ruta que escribió el sink.

    `path` es la que asignó `ConversationPaths` (puede llevar sufijo de desempate); sin
    ella se usa la ruta natural de la conversación.
    """
    return IndexEntry(
        id=conversation.id,
        title=conversation_title(conversation),
        path=path if path is not None else conversation_output_path(conversation),
        date=conversation_date(conversation),
        project_id=conversation.project_id,
        message_count=len(conversation.messages),
    )


def memory_entry(memory: Memory, path: str) -> IndexEntry:
    """Fila del índice de una memoria; `path` es el que asignó `assign_output_paths`."""
    return IndexEntry(
        id=memory.path,
        title=memory_title(memory),
        path=path,
        date=memory.updated_at,
        project_id=memory.project_id,
    )


def index_sort_key(entry: IndexEntry) -> tuple[bool, float, str]:
    """Fecha descendente, sin fecha al final, desempate por `id` (determinismo, CA-1)."""
    return (entry.date is None, -(entry.date or _NO_DATE).timestamp(), entry.id)


def sort_entries(entries: Iterable[IndexEntry]) -> list[IndexEntry]:
    """Las filas en el orden en que se imprimen (spec 04 CA-7)."""
    return sorted(entries, key=index_sort_key)


def _day(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).strftime(DAY)


def _row(entry: IndexEntry) -> dict[str, Any]:
    return {
        "day": _day(entry.date),
        "title": entry.title,
        "link": entry.path,
        "project": entry.project_id,
        "messages": entry.message_count,
    }


def index_context(
    conversations: Iterable[IndexEntry] = (),
    memories: Iterable[IndexEntry] = (),
) -> dict[str, Any]:
    """Variables que ve `index.md.j2` (documentadas en la propia plantilla)."""
    conversation_rows = [_row(entry) for entry in sort_entries(conversations)]
    memory_rows = [_row(entry) for entry in sort_entries(memories)]
    return {
        "conversations": conversation_rows,
        "memories": memory_rows,
        "conversation_count": len(conversation_rows),
        "memory_count": len(memory_rows),
    }


def render_index(
    conversations: Iterable[IndexEntry] = (),
    memories: Iterable[IndexEntry] = (),
    environment: Environment | None = None,
) -> str:
    """Markdown del `_index.md` de la raíz de la salida (spec 04 CA-7)."""
    env = environment if environment is not None else build_environment()
    rendered = env.get_template(INDEX_TEMPLATE).render(**index_context(conversations, memories))
    return rendered.rstrip("\n") + "\n"


def readme_context(
    source: str,
    format_version: str,
    counts: dict[str, int],
    export_created_at: str | None = None,
    missing_categories: Sequence[str] = (),
) -> dict[str, Any]:
    """Variables que ve `readme.md.j2` (documentadas en la propia plantilla)."""
    return {
        "source": source,
        "format_version": format_version,
        "counts": dict(sorted(counts.items())),
        "export_created_at": export_created_at,
        "missing_categories": list(missing_categories),
    }


def render_readme(
    source: str,
    format_version: str,
    counts: dict[str, int],
    export_created_at: str | None = None,
    missing_categories: Sequence[str] = (),
    environment: Environment | None = None,
) -> str:
    """Markdown del `README.md` de la raíz: qué es esto y de qué export salió."""
    env = environment if environment is not None else build_environment()
    rendered = env.get_template(README_TEMPLATE).render(
        **readme_context(source, format_version, counts, export_created_at, missing_categories)
    )
    return rendered.rstrip("\n") + "\n"


__all__ = [
    "DAY",
    "ERRORS_NAME",
    "ERRORS_PATH",
    "INDEX_NAME",
    "INDEX_TEMPLATE",
    "INVENTORY_NAME",
    "INVENTORY_PATH",
    "README_NAME",
    "README_TEMPLATE",
    "REPORT_DIR",
    "SUMMARY_NAME",
    "SUMMARY_PATH",
    "IndexEntry",
    "conversation_entry",
    "index_context",
    "index_sort_key",
    "memory_entry",
    "readme_context",
    "render_index",
    "render_readme",
    "sort_entries",
]
