"""Cruce conversación ↔ proyecto (spec 03, `projects` CA-4; spec 04 CA-7).

El archivo de un proyecto NO lista sus conversaciones: el enlace viaja al revés, en
`conversations[].project_uuid`. Ninguna de las dos categorías puede resolverlo sola, así
que el cruce no es de un parser (que ve un archivo) ni de `rendering/` (que ve una
entidad): es orquestación, y vive aquí, entre las dos colecciones.

Decisiones:

* **Streaming intacto.** Los proyectos son pocos (32 archivos, 22 KB en el export real)
  y se retienen enteros; las conversaciones siguen pasando de una en una (CLAUDE.md §4).
  De cada una solo se guarda un `ConversationLink` diminuto —id, título, ruta y fecha—
  para que su proyecto pueda enumerarla al final.
* **Las carpetas se reparten una sola vez.** `assign_project_dirs` (el mismo desempate
  que usa el render) se llama aquí, en el constructor, de modo que el `project.md`, el
  enlace que escribe cada conversación y la fila del `_index.md` nombren siempre el
  mismo archivo.
* **Si no resuelve, no se inventa nada.** Una conversación cuyo `project_uuid` no está
  en el export conserva su uuid crudo (es lo que trae el export) y no recibe enlace. No
  es un error del ítem —la conversación se convierte igual—, pero tampoco se calla
  (CLAUDE.md §1.3): queda UNA advertencia agregada por corrida, no una por conversación,
  porque un export sin la categoría `projects` dispararía cientos de líneas idénticas.
* **Determinista.** El orden de las conversaciones de un proyecto es el mismo del
  `_index.md` (fecha descendente, sin fecha al final, desempate por id) y los uuids de
  la advertencia van ordenados: dos corridas escriben los mismos bytes (spec 04 CA-1).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from claude_export_md.domain.entities import Conversation, Project
from claude_export_md.rendering.conversations import conversation_date, conversation_title
from claude_export_md.rendering.links import (
    ConversationLink,
    ProjectLink,
    conversation_link_sort_key,
)
from claude_export_md.rendering.render import (
    assign_project_dirs,
    project_output_path,
    project_title,
)

#: Advertencia única de la corrida cuando alguna conversación apunta a un proyecto que
#: el export no trae (categoría ausente, export parcial, proyecto borrado…).
#: `{conversations}` y `{projects}` llegan ya pluralizados (`1 proyecto` / `3 proyectos`).
ORPHAN_PROJECTS_WARNING = (
    "{conversations} {verb} a {projects} que este export no trae; se conserva su uuid "
    "sin enlace: {ids}"
)


def _plural(count: int, singular: str, plural: str) -> str:
    """`1 proyecto` / `3 proyectos` (mismo criterio que el resumen del CLI)."""
    return f"{count} {singular if count == 1 else plural}"


@dataclass(frozen=True, slots=True)
class ResolvedProject:
    """Un proyecto listo para renderizar, ya con sus conversaciones resueltas."""

    #: El proyecto del parser con `conversation_ids` poblado (CA-4).
    project: Project
    #: `projects/<slug>`, la carpeta que le tocó tras desempatar colisiones.
    directory: str
    #: Sus conversaciones, en el orden en que las enumera el `project.md`.
    conversations: tuple[ConversationLink, ...]


class ProjectLinker:
    """Resuelve el enlace en las dos direcciones mientras la conversión avanza.

    Se construye con los proyectos ya parseados y se le va dando cada conversación con
    la ruta que el sink acaba de escribir (`record`). Al final, `resolved()` devuelve
    cada proyecto con sus conversaciones.
    """

    def __init__(self, projects: Iterable[Project] = ()) -> None:
        self._assigned = assign_project_dirs(list(projects))
        self._links = {
            project.id: ProjectLink(
                id=project.id,
                title=project_title(project),
                path=project_output_path(project, directory),
            )
            for project, directory in self._assigned
        }
        self._conversations: dict[str, list[ConversationLink]] = {
            project.id: [] for project, _directory in self._assigned
        }
        self._orphans: dict[str, int] = {}

    # ------------------------------------------------- conversación → proyecto

    def link(self, project_id: str | None) -> ProjectLink | None:
        """El proyecto al que apunta un `project_uuid`, o `None` si no se conoce."""
        if not project_id:
            return None
        return self._links.get(project_id)

    def record(self, conversation: Conversation, path: str) -> ProjectLink | None:
        """Anota la conversación bajo su proyecto y devuelve el enlace a ese proyecto.

        `path` es la ruta que el sink escribió (ya desempatada), para que el
        `project.md` enlace el archivo que de verdad existe.
        """
        project_id = conversation.project_id
        if not project_id:
            return None
        link = self._links.get(project_id)
        if link is None:
            self._orphans[project_id] = self._orphans.get(project_id, 0) + 1
            return None
        self._conversations[project_id].append(
            ConversationLink(
                id=conversation.id,
                title=conversation_title(conversation),
                path=path,
                date=conversation_date(conversation),
            )
        )
        return link

    # ------------------------------------------------- proyecto → conversaciones

    def conversations(self, project_id: str) -> tuple[ConversationLink, ...]:
        """Las conversaciones de un proyecto, en el orden del `_index.md`."""
        return tuple(
            sorted(self._conversations.get(project_id, ()), key=conversation_link_sort_key)
        )

    def resolved(self) -> list[ResolvedProject]:
        """Cada proyecto con su carpeta y sus conversaciones, en el orden de entrada."""
        resolved = []
        for project, directory in self._assigned:
            links = self.conversations(project.id)
            resolved.append(
                ResolvedProject(
                    project=project.model_copy(
                        update={"conversation_ids": [link.id for link in links]}
                    ),
                    directory=directory,
                    conversations=links,
                )
            )
        return resolved

    # -------------------------------------------------------------- advertencias

    @property
    def orphan_project_ids(self) -> list[str]:
        """Los `project_uuid` que ninguna entidad del export explica, ordenados."""
        return sorted(self._orphans)

    @property
    def warnings(self) -> Sequence[str]:
        """Una sola línea por corrida (ver las decisiones del módulo)."""
        if not self._orphans:
            return []
        conversations = sum(self._orphans.values())
        return [
            ORPHAN_PROJECTS_WARNING.format(
                conversations=_plural(conversations, "conversación", "conversaciones"),
                verb="apunta" if conversations == 1 else "apuntan",
                projects=_plural(len(self._orphans), "proyecto", "proyectos"),
                ids=", ".join(self.orphan_project_ids),
            )
        ]


__all__ = [
    "ORPHAN_PROJECTS_WARNING",
    "ProjectLinker",
    "ResolvedProject",
]
