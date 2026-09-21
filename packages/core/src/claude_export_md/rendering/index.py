"""Índice global (`_index.md`) y portada (`README.md`) de la salida.

Módulo puro, como el resto de `rendering/`: arma texto a partir de lo que ya se
convirtió y no escribe nada ni mira el reloj. La única fecha que puede aparecer aquí es
la del MANIFIESTO del export (cuándo lo generó Anthropic), nunca la de la corrida
(CLAUDE.md §1.4).

Decisiones:

* **Qué lleva el índice** — spec 04 CA-7 solo exige la tabla de conversaciones (fecha
  descendente, enlace relativo, proyecto y nº de mensajes). Desde M2 hay una sección por
  categoría convertida —conversaciones, proyectos, memorias, artefactos y la cuenta—
  porque un índice que nombrara solo una parte dejaría el resto del árbol sin puerta de
  entrada. Cada una es una sección independiente, así que una plantilla propia puede
  quitar la que no le interese sin tocar las demás.
* **Proyecto de una conversación** — si `Conversation.project_id` resuelve a un proyecto
  del export (lo cruza `usecases/links.py`), la columna muestra su NOMBRE con enlace
  relativo a `projects/<slug>/project.md`; si no resuelve —proyecto ausente o export sin
  `projects`— se imprime el `project_uuid` crudo, que es lo que trae el export, en vez
  de dejar la celda vacía o inventar un enlace roto.
* **Orden** — fecha descendente y, a igualdad, `id` ascendente. Lo que no tiene fecha va
  al final (no se le inventa una) y también se ordena por `id`, para que dos corridas
  produzcan exactamente el mismo archivo. La clave es la misma de `rendering/links.py`,
  compartida con el `project.md`.
* **Celdas** — el título es texto libre del usuario: se escapa con el filtro `md_cell`,
  porque un `|` o un salto de línea partirían la tabla.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jinja2 import Environment

from claude_export_md.domain.entities import Account, Conversation, Frame, Memory, Project
from claude_export_md.rendering.conversations import (
    conversation_date,
    conversation_output_path,
    conversation_title,
)
from claude_export_md.rendering.links import DAY, ProjectLink, date_sort_key, day
from claude_export_md.rendering.render import (
    DOC_STATUS_AVAILABLE,
    DOC_STATUS_UNAVAILABLE,
    account_title,
    build_environment,
    frame_title,
    memory_title,
    project_title,
)

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


@dataclass(frozen=True, slots=True)
class IndexEntry:
    """Una fila del índice, de la categoría que sea.

    Es deliberadamente diminuta: `convert` la va acumulando mientras escribe en
    streaming, de modo que en memoria queden las ~291 filas del índice y no las ~291
    conversaciones enteras. Cada sección usa un subconjunto de los campos (una memoria
    no tiene documentos, un proyecto no tiene mensajes) y los que no le tocan van en
    `None`, que la plantilla imprime como celda vacía.
    """

    id: str
    title: str
    path: str
    date: datetime | None = None
    #: `project_uuid` tal cual vino en el export (aunque no resuelva).
    project_id: str | None = None
    #: El proyecto ya resuelto a nombre y archivo, si el export lo trae.
    project: ProjectLink | None = None
    message_count: int | None = None
    #: Solo en los proyectos: cuántos documentos y cuántas conversaciones tienen.
    doc_count: int | None = None
    conversation_count: int | None = None
    #: Solo en los artefactos: qué dice el export que son y si trae su contenido.
    kind: str | None = None
    content_available: bool | None = None


def conversation_entry(
    conversation: Conversation, path: str | None = None, project: ProjectLink | None = None
) -> IndexEntry:
    """Fila del índice de una conversación, con la misma ruta que escribió el sink.

    `path` es la que asignó `ConversationPaths` (puede llevar sufijo de desempate); sin
    ella se usa la ruta natural de la conversación. `project` es el proyecto ya resuelto
    por `usecases/links.py`; sin él la columna muestra el uuid crudo.
    """
    return IndexEntry(
        id=conversation.id,
        title=conversation_title(conversation),
        path=path if path is not None else conversation_output_path(conversation),
        date=conversation_date(conversation),
        project_id=conversation.project_id,
        project=project,
        message_count=len(conversation.messages),
    )


def memory_entry(memory: Memory, path: str, project: ProjectLink | None = None) -> IndexEntry:
    """Fila del índice de una memoria; `path` es el que asignó `assign_output_paths`.

    Las memorias de proyecto (ADR-0005) llevan `project_id`: si el export trae ese
    proyecto, la columna lo nombra y lo enlaza igual que en las conversaciones.
    """
    return IndexEntry(
        id=memory.path,
        title=memory_title(memory),
        path=path,
        date=memory.updated_at,
        project_id=memory.project_id,
        project=project,
    )


def project_entry(project: Project, path: str) -> IndexEntry:
    """Fila del índice de un proyecto; `path` es su `projects/<slug>/project.md`.

    `conversation_ids` ya viene poblado por `usecases/links.py` (spec 03, projects
    CA-4): aquí solo se cuenta.
    """
    return IndexEntry(
        id=project.id,
        title=project_title(project),
        path=path,
        date=project.updated_at or project.created_at,
        doc_count=len(project.docs),
        conversation_count=len(project.conversation_ids),
    )


def frame_entry(frame: Frame, path: str) -> IndexEntry:
    """Fila del índice de un artefacto; `path` es el que asignó `assign_frame_paths`."""
    return IndexEntry(
        id=frame.id,
        title=frame_title(frame),
        path=path,
        date=frame.updated_at,
        kind=frame.kind,
        # Spec 03, frames CA-2: ningún campo observado trae el contenido del artefacto.
        # El día que se sepa dónde vive, este valor saldrá de la entidad.
        content_available=False,
    )


def account_entry(account: Account, path: str) -> IndexEntry:
    """Fila del índice del perfil de la cuenta; `path` es `account/account.md`."""
    return IndexEntry(id=account.id, title=account_title(account), path=path)


def index_sort_key(entry: IndexEntry) -> tuple[bool, float, str]:
    """Fecha descendente, sin fecha al final, desempate por `id` (determinismo, CA-1)."""
    return date_sort_key(entry.date, entry.id)


def sort_entries(entries: Iterable[IndexEntry]) -> list[IndexEntry]:
    """Las filas en el orden en que se imprimen (spec 04 CA-7)."""
    return sorted(entries, key=index_sort_key)


def _row(entry: IndexEntry) -> dict[str, Any]:
    """Una fila de tabla: el `_index.md` está en la raíz, así que `path` ya es relativa."""
    return {
        "day": day(entry.date),
        "title": entry.title,
        "link": entry.path,
        # El nombre del proyecto si resolvió; si no, el uuid crudo del export.
        "project": entry.project.title if entry.project is not None else entry.project_id,
        "project_link": entry.project.path if entry.project is not None else None,
        "messages": entry.message_count,
        "docs": entry.doc_count,
        "conversations": entry.conversation_count,
        "kind": entry.kind,
        "content": _content_cell(entry.content_available),
    }


def _content_cell(available: bool | None) -> str | None:
    if available is None:
        return None
    return DOC_STATUS_AVAILABLE if available else DOC_STATUS_UNAVAILABLE


def _rows(entries: Iterable[IndexEntry]) -> list[dict[str, Any]]:
    return [_row(entry) for entry in sort_entries(entries)]


def index_context(
    conversations: Iterable[IndexEntry] = (),
    memories: Iterable[IndexEntry] = (),
    projects: Iterable[IndexEntry] = (),
    frames: Iterable[IndexEntry] = (),
    accounts: Iterable[IndexEntry] = (),
) -> dict[str, Any]:
    """Variables que ve `index.md.j2` (documentadas en la propia plantilla)."""
    sections = {
        "conversations": _rows(conversations),
        "memories": _rows(memories),
        "projects": _rows(projects),
        "frames": _rows(frames),
        "accounts": _rows(accounts),
    }
    # Un contador por sección: la plantilla los usa para el título y para no imprimir
    # una tabla vacía. Los nombres son fijos (no derivados) porque "memories" no
    # singulariza quitando la `s`.
    counts = {
        "conversation_count": len(sections["conversations"]),
        "memory_count": len(sections["memories"]),
        "project_count": len(sections["projects"]),
        "frame_count": len(sections["frames"]),
        "account_count": len(sections["accounts"]),
    }
    return {**sections, **counts}


def render_index(
    conversations: Iterable[IndexEntry] = (),
    memories: Iterable[IndexEntry] = (),
    projects: Iterable[IndexEntry] = (),
    frames: Iterable[IndexEntry] = (),
    accounts: Iterable[IndexEntry] = (),
    environment: Environment | None = None,
) -> str:
    """Markdown del `_index.md` de la raíz de la salida (spec 04 CA-7)."""
    env = environment if environment is not None else build_environment()
    rendered = env.get_template(INDEX_TEMPLATE).render(
        **index_context(conversations, memories, projects, frames, accounts)
    )
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
    "account_entry",
    "conversation_entry",
    "frame_entry",
    "index_context",
    "index_sort_key",
    "memory_entry",
    "project_entry",
    "readme_context",
    "render_index",
    "render_readme",
    "sort_entries",
]
