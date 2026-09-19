"""Enlaces entre archivos del árbol de salida (spec 04 CA-7, spec 03 projects CA-4).

Módulo puro y diminuto: no conoce entidades del dominio, solo `(id, título, ruta)`. Vive
aparte de `render.py` para que las tres partes que necesitan enlazarse entre sí
—conversaciones, proyectos y el `_index.md`— compartan el mismo vocabulario sin
importarse unas a otras.

Quién los construye: `usecases/links.py`, que es el único sitio donde se cruzan las dos
colecciones (`Conversation.project_id` con `Project.id`). El render solo los consume.

Todas las rutas que se manejan aquí son relativas a la RAÍZ de la salida y en formato
POSIX, igual que las del puerto `MarkdownSink` (ADR-0006); `relative_link` las convierte
al enlace que hay que escribir DENTRO de un archivo concreto.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from datetime import UTC, datetime

#: Formato de la columna de fecha de las tablas del índice.
DAY = "%Y-%m-%d"

#: Fecha con la que se ordena lo que no tiene ninguna: va al final y no se le inventa una.
_NO_DATE = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class ProjectLink:
    """El proyecto al que apunta una conversación, ya resuelto a nombre y archivo."""

    id: str
    title: str
    #: `projects/<slug>/project.md`, relativa a la raíz de la salida.
    path: str


@dataclass(frozen=True, slots=True)
class ConversationLink:
    """Una conversación que apunta a un proyecto, tal como la enumera su `project.md`."""

    id: str
    title: str
    #: `conversations/YYYY/MM/….md`, la misma ruta que escribió el sink.
    path: str
    date: datetime | None = None


def relative_link(from_path: str, to_path: str) -> str:
    """Enlace a `to_path` escrito dentro de `from_path` (ambas desde la raíz).

    `conversations/2026/01/x.md` → `projects/cocina/project.md` da
    `../../../projects/cocina/project.md`. Es `posixpath`, no `os.path`: el resultado
    tiene que ser el mismo en Windows y en Linux (CLAUDE.md §1.4).
    """
    return posixpath.relpath(to_path, posixpath.dirname(from_path))


def day(value: datetime | None) -> str | None:
    """`YYYY-MM-DD` en UTC, o `None` si el export no trajo fecha (nunca se inventa)."""
    return None if value is None else value.astimezone(UTC).strftime(DAY)


def date_sort_key(value: datetime | None, identifier: str) -> tuple[bool, float, str]:
    """Fecha descendente, sin fecha al final, desempate por identificador (CA-1)."""
    return (value is None, -(value or _NO_DATE).timestamp(), identifier)


def conversation_link_sort_key(link: ConversationLink) -> tuple[bool, float, str]:
    """Orden en que un `project.md` enumera sus conversaciones: el del `_index.md`."""
    return date_sort_key(link.date, link.id)


__all__ = [
    "DAY",
    "ConversationLink",
    "ProjectLink",
    "conversation_link_sort_key",
    "date_sort_key",
    "day",
    "relative_link",
]
