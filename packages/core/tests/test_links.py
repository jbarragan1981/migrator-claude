"""Enlace conversación ↔ proyecto (spec 03, `projects` CA-4; spec 04 CA-7).

Dos piezas, dos secciones:

* `rendering/links.py` — el vocabulario común (`ProjectLink`, `ConversationLink`) y las
  funciones puras de ruta/fecha/orden que comparten el `_index.md`, el `project.md` y el
  `conversation.md`.
* `usecases/links.py` — el ÚNICO sitio donde se cruzan las dos colecciones: qué proyecto
  tiene cada conversación y qué conversaciones tiene cada proyecto.

Un test por regla. Todos los datos son sintéticos.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from claude_export_md.domain.entities import Conversation, Project
from claude_export_md.rendering.links import (
    ConversationLink,
    ProjectLink,
    conversation_link_sort_key,
    date_sort_key,
    day,
    relative_link,
)
from claude_export_md.usecases.links import ORPHAN_PROJECTS_WARNING, ProjectLinker

PROJECT_1 = "ffffffff-0000-4000-8000-000000000001"
PROJECT_2 = "ffffffff-0000-4000-8000-000000000002"
UNKNOWN_PROJECT = "00000000-dead-4000-8000-000000000000"
CONVERSATION_1 = "a1a1a1a1-1111-4000-8000-000000000001"
CONVERSATION_2 = "b2b2b2b2-2222-4000-8000-000000000002"


def at(day_of_month: int) -> datetime:
    return datetime(2026, 3, day_of_month, 9, 0, tzinfo=UTC)


def make_project(**values: Any) -> Project:
    return Project.model_validate({"id": PROJECT_1, "name": "Cocina casera", **values})


def make_conversation(**values: Any) -> Conversation:
    return Conversation.model_validate(
        {
            "id": CONVERSATION_1,
            "title": "Receta de arepas",
            "created_at": at(3),
            "project_id": PROJECT_1,
            "messages": [],
            **values,
        }
    )


# ============================================================ rendering/links.py


def test_a_link_from_a_conversation_to_a_project_climbs_out_of_its_year_and_month() -> None:
    link = relative_link(
        "conversations/2026/01/2026-01-15_receta_a1a1a1a1.md", "projects/cocina/project.md"
    )

    assert link == "../../../projects/cocina/project.md"


def test_a_link_from_a_project_to_a_conversation_is_the_way_back() -> None:
    link = relative_link(
        "projects/cocina/project.md", "conversations/2026/01/2026-01-15_receta_a1a1a1a1.md"
    )

    assert link == "../../conversations/2026/01/2026-01-15_receta_a1a1a1a1.md"


def test_a_link_from_the_root_index_is_the_path_itself() -> None:
    assert relative_link("_index.md", "projects/cocina/project.md") == "projects/cocina/project.md"


def test_links_are_posix_even_on_windows() -> None:
    """CLAUDE.md §1.4: el mismo export tiene que dar el mismo texto en los dos sistemas."""
    assert "\\" not in relative_link("conversations/2026/01/x.md", "projects/cocina/project.md")


def test_the_day_of_a_date_is_utc() -> None:
    assert day(datetime(2026, 1, 15, 23, 30, tzinfo=UTC)) == "2026-01-15"


def test_without_a_date_there_is_no_day_invented() -> None:
    assert day(None) is None


def test_dates_sort_newest_first_and_undated_last() -> None:
    items = [(None, "z"), (at(1), "c"), (at(3), "a"), (at(2), "b")]

    ordered = sorted(items, key=lambda item: date_sort_key(*item))

    assert [identifier for _date, identifier in ordered] == ["a", "b", "c", "z"]


def test_two_items_with_the_same_date_tie_break_by_identifier() -> None:
    items = [(at(1), "b"), (at(1), "a")]

    assert [i for _d, i in sorted(items, key=lambda item: date_sort_key(*item))] == ["a", "b"]


def test_conversation_links_sort_like_the_index() -> None:
    links = [
        ConversationLink(id="b", title="B", path="b.md", date=at(1)),
        ConversationLink(id="z", title="Z", path="z.md"),
        ConversationLink(id="a", title="A", path="a.md", date=at(2)),
    ]

    ordered = sorted(links, key=conversation_link_sort_key)

    assert [link.id for link in ordered] == ["a", "b", "z"]


# ============================================================== usecases/links.py


def test_a_conversation_resolves_to_the_name_and_file_of_its_project() -> None:
    """Spec 03, projects CA-4: el cruce es `Conversation.project_id` ↔ `Project.id`."""
    linker = ProjectLinker([make_project()])

    link = linker.link(PROJECT_1)

    assert link == ProjectLink(
        id=PROJECT_1, title="Cocina casera", path="projects/cocina-casera/project.md"
    )


def test_a_conversation_without_project_resolves_to_nothing() -> None:
    linker = ProjectLinker([make_project()])

    assert linker.link(None) is None


def test_a_project_that_is_not_in_the_export_does_not_resolve() -> None:
    """Sin proyecto no se inventa uno: quien llama mantiene el uuid crudo."""
    linker = ProjectLinker([make_project()])

    assert linker.link(UNKNOWN_PROJECT) is None


def test_an_export_without_projects_resolves_nothing_and_does_not_break() -> None:
    linker = ProjectLinker([])

    assert linker.link(PROJECT_1) is None
    assert linker.resolved() == []


def test_recording_a_conversation_returns_its_project_link() -> None:
    linker = ProjectLinker([make_project()])

    link = linker.record(make_conversation(), "conversations/2026/03/x.md")

    assert link is not None
    assert link.title == "Cocina casera"


def test_the_project_lists_the_conversations_that_point_at_it() -> None:
    linker = ProjectLinker([make_project()])
    linker.record(make_conversation(), "conversations/2026/03/a.md")
    linker.record(
        make_conversation(id=CONVERSATION_2, title="Otra", created_at=at(1)),
        "conversations/2026/03/b.md",
    )

    resolved = linker.resolved()

    assert [link.title for link in resolved[0].conversations] == ["Receta de arepas", "Otra"]
    assert resolved[0].conversations[0].path == "conversations/2026/03/a.md"


def test_the_conversations_of_a_project_are_newest_first() -> None:
    linker = ProjectLinker([make_project()])
    linker.record(make_conversation(created_at=at(1)), "conversations/2026/03/a.md")
    linker.record(
        make_conversation(id=CONVERSATION_2, title="Otra", created_at=at(5)),
        "conversations/2026/03/b.md",
    )

    assert [link.id for link in linker.resolved()[0].conversations] == [
        CONVERSATION_2,
        CONVERSATION_1,
    ]


def test_the_resolved_project_carries_the_conversation_ids_of_the_entity() -> None:
    """CA-4: `Project.conversation_ids` lo puebla el cruce, no el parser."""
    linker = ProjectLinker([make_project()])
    linker.record(make_conversation(), "conversations/2026/03/a.md")

    project = linker.resolved()[0].project

    assert project.conversation_ids == [CONVERSATION_1]
    # No se pierde nada del proyecto original.
    assert project.name == "Cocina casera"


def test_a_project_without_conversations_stays_empty_and_is_still_resolved() -> None:
    linker = ProjectLinker([make_project()])

    resolved = linker.resolved()

    assert len(resolved) == 1
    assert resolved[0].project.conversation_ids == []
    assert resolved[0].directory == "projects/cocina-casera"


def test_two_projects_with_the_same_name_get_their_own_folder() -> None:
    """El desempate es el mismo que ya hacía el render: el hash corto del id."""
    linker = ProjectLinker([make_project(), make_project(id=PROJECT_2)])

    directories = [resolved.directory for resolved in linker.resolved()]

    assert len(set(directories)) == 2
    assert all(directory.startswith("projects/cocina-casera-") for directory in directories)


def test_the_link_of_a_disambiguated_project_points_at_its_own_folder() -> None:
    linker = ProjectLinker([make_project(), make_project(id=PROJECT_2)])

    link = linker.link(PROJECT_2)

    assert link is not None
    assert link.path.startswith("projects/cocina-casera-")
    assert link.path.endswith("/project.md")


def test_an_orphan_conversation_leaves_one_warning_for_the_whole_run() -> None:
    """CLAUDE.md §1.3: no se calla, pero tampoco una advertencia por conversación."""
    linker = ProjectLinker([])
    linker.record(make_conversation(), "conversations/2026/03/a.md")
    linker.record(make_conversation(id=CONVERSATION_2), "conversations/2026/03/b.md")

    assert linker.warnings == [
        ORPHAN_PROJECTS_WARNING.format(
            conversations="2 conversaciones",
            verb="apuntan",
            projects="1 proyecto",
            ids=PROJECT_1,
        )
    ]


def test_the_orphan_warning_is_written_in_singular_when_there_is_only_one() -> None:
    """Detalle de revisión: nunca "2 conversaciones apuntan a 1 proyectos"."""
    linker = ProjectLinker([])
    linker.record(make_conversation(), "conversations/2026/03/a.md")

    assert linker.warnings == [
        ORPHAN_PROJECTS_WARNING.format(
            conversations="1 conversación",
            verb="apunta",
            projects="1 proyecto",
            ids=PROJECT_1,
        )
    ]


def test_without_orphans_there_is_no_warning() -> None:
    linker = ProjectLinker([make_project()])
    linker.record(make_conversation(), "conversations/2026/03/a.md")
    linker.record(make_conversation(id=CONVERSATION_2, project_id=None), "x.md")

    assert linker.warnings == []


def test_the_orphan_warning_lists_the_missing_uuids_in_a_stable_order() -> None:
    linker = ProjectLinker([])
    linker.record(make_conversation(project_id=PROJECT_2), "a.md")
    linker.record(make_conversation(id=CONVERSATION_2, project_id=PROJECT_1), "b.md")

    assert f"{PROJECT_1}, {PROJECT_2}" in linker.warnings[0]


def test_the_same_conversations_and_projects_always_produce_the_same_links() -> None:
    """CA-1: el cruce no depende del orden ni de la corrida."""

    def run(order: list[Conversation]) -> list[tuple[str, tuple[str, ...]]]:
        linker = ProjectLinker([make_project(), make_project(id=PROJECT_2, name="Otro")])
        for conversation in order:
            linker.record(conversation, f"conversations/2026/03/{conversation.id}.md")
        return [
            (resolved.directory, tuple(link.id for link in resolved.conversations))
            for resolved in linker.resolved()
        ]

    first = make_conversation()
    second = make_conversation(id=CONVERSATION_2, project_id=PROJECT_2, created_at=at(1))

    assert run([first, second]) == run([second, first])
