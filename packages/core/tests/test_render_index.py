"""Render del `_index.md` y del `README.md` (spec 04 CA-7, CLAUDE.md §5).

Módulo puro: aquí se prueba el TEXTO, sin tocar el disco. El árbol completo y su
determinismo se prueban en `test_convert.py`. El snapshot (`syrupy`) es la red de
seguridad del formato: si cambia una línea de la tabla, el diff lo enseña.
"""

from __future__ import annotations

from datetime import UTC, datetime

from syrupy.assertion import SnapshotAssertion

from claude_export_md.domain.entities import (
    Account,
    Conversation,
    Frame,
    Project,
    ProjectDoc,
    conversations_memory,
    memory_from_file,
)
from claude_export_md.rendering.index import (
    IndexEntry,
    account_entry,
    conversation_entry,
    frame_entry,
    memory_entry,
    project_entry,
    render_index,
    render_readme,
    sort_entries,
)
from claude_export_md.rendering.links import ProjectLink


def at(day: int) -> datetime:
    return datetime(2026, 3, day, 9, 0, tzinfo=UTC)


ENTRIES = [
    IndexEntry(id="c", title="Tercera", path="conversations/2026/03/c.md", date=at(1)),
    IndexEntry(id="a", title="Primera", path="conversations/2026/03/a.md", date=at(3)),
    IndexEntry(id="b", title="Segunda", path="conversations/2026/03/b.md", date=at(2)),
    IndexEntry(id="z", title="Sin fecha", path="conversations/sin-fecha/z.md"),
]

PROJECT = "ffffffff-0000-4000-8000-000000000001"
COCINA = ProjectLink(id=PROJECT, title="Cocina casera", path="projects/cocina-casera/project.md")


def make_conversation(**values: object) -> Conversation:
    return Conversation.model_validate(
        {
            "id": "a1a1a1a1-1111-4000-8000-000000000001",
            "title": "Análisis Ñandú / Q3",
            "created_at": "2026-01-15T14:32:05Z",
            "project_id": PROJECT,
            "messages": [{"id": "m1", "sender": "human", "text": "hola"}],
            **values,
        }
    )


def test_ca7_entries_are_sorted_by_date_descending() -> None:
    assert [entry.id for entry in sort_entries(ENTRIES)] == ["a", "b", "c", "z"]


def test_entries_without_date_go_last_and_tie_break_by_id() -> None:
    undated = [
        IndexEntry(id="b", title="B", path="b.md"),
        IndexEntry(id="a", title="A", path="a.md"),
    ]

    assert [entry.id for entry in sort_entries(undated)] == ["a", "b"]


def test_two_entries_with_the_same_date_tie_break_by_id() -> None:
    same = [
        IndexEntry(id="b", title="B", path="b.md", date=at(1)),
        IndexEntry(id="a", title="A", path="a.md", date=at(1)),
    ]

    assert [entry.id for entry in sort_entries(same)] == ["a", "b"]


def test_a_conversation_entry_uses_the_same_path_the_sink_writes() -> None:
    entry = conversation_entry(make_conversation())

    assert entry.path == "conversations/2026/01/2026-01-15_analisis-nandu-q3_a1a1a1a1.md"
    assert entry.message_count == 1
    assert entry.project_id == PROJECT


def test_a_resolved_project_is_shown_by_name_and_linked() -> None:
    """CA-7: con el proyecto resuelto, la columna deja de ser un uuid."""
    markdown = render_index([conversation_entry(make_conversation(), project=COCINA)])

    assert "[Cocina casera](projects/cocina-casera/project.md)" in markdown
    assert PROJECT not in markdown


def test_an_unresolved_project_keeps_the_raw_uuid_without_a_link() -> None:
    """Un export sin `projects` (o con el proyecto ausente) no inventa un enlace roto."""
    markdown = render_index([conversation_entry(make_conversation())])

    assert PROJECT in markdown
    assert "](projects/" not in markdown


def test_a_project_entry_counts_its_docs_and_its_conversations() -> None:
    project = Project.model_validate(
        {
            "id": PROJECT,
            "name": "Cocina casera",
            "updated_at": "2026-03-01T00:00:00Z",
            "docs": [ProjectDoc(id="d1"), ProjectDoc(id="d2")],
            "conversation_ids": ["c1"],
        }
    )

    entry = project_entry(project, "projects/cocina-casera/project.md")

    assert entry.title == "Cocina casera"
    assert entry.doc_count == 2
    assert entry.conversation_count == 1


def test_a_frame_entry_says_that_the_export_does_not_bring_the_content() -> None:
    """Spec 03, frames CA-2: el índice no puede sugerir que el artefacto está entero."""
    frame = Frame.model_validate({"id": "f1", "kind": "document", "versions": []})

    markdown = render_index(frames=[frame_entry(frame, "frames/f1.md")])

    assert "No disponible en este export" in markdown
    assert "document" in markdown


def test_an_account_entry_is_listed_with_its_name() -> None:
    account = Account.model_validate({"id": "acc", "display_name": "Persona Ñandú"})

    markdown = render_index(accounts=[account_entry(account, "account/account.md")])

    assert "- [Persona Ñandú](account/account.md)" in markdown


def test_a_memory_entry_takes_the_path_that_was_assigned_to_it() -> None:
    memory = memory_from_file({"path": "/people/Ana María.md", "content": "x"})

    entry = memory_entry(memory, "memories/people/ana-maria.md")

    assert entry.title == "Ana María"
    assert entry.path == "memories/people/ana-maria.md"
    assert entry.message_count is None


def test_an_empty_index_says_so_instead_of_printing_an_empty_table() -> None:
    markdown = render_index()

    assert "No se convirtió ningún ítem" in markdown
    assert "|" not in markdown


def test_the_readme_without_export_date_does_not_print_the_row() -> None:
    markdown = render_readme("mi-export", "batched-manifest", {"memories": 2})

    assert "Fecha del export" not in markdown
    assert "`mi-export`" in markdown


# ------------------------------------------------------------------ snapshot


def test_snapshot_of_the_index(snapshot: SnapshotAssertion) -> None:
    """Las cinco secciones del índice, cada una con al menos una fila."""
    memories = [memory_entry(conversations_memory("x"), "memories/conversations-memory.md")]
    projects = [
        project_entry(
            Project.model_validate(
                {
                    "id": PROJECT,
                    "name": "Cocina casera",
                    "updated_at": "2026-03-04T00:00:00Z",
                    "docs": [ProjectDoc(id="d1")],
                    "conversation_ids": ["a"],
                }
            ),
            "projects/cocina-casera/project.md",
        )
    ]
    frames = [
        frame_entry(
            Frame.model_validate(
                {
                    "id": "f1f1f1f1",
                    "kind": "document",
                    "updated_at": "2026-03-02T00:00:00Z",
                    "versions": [{"id": "v1", "title": "Informe de ventas Q3"}],
                }
            ),
            "frames/informe-de-ventas-q3.md",
        )
    ]
    accounts = [
        account_entry(
            Account.model_validate({"id": "acc", "display_name": "Persona Ñandú"}),
            "account/account.md",
        )
    ]
    conversations = [*ENTRIES, conversation_entry(make_conversation(), project=COCINA)]

    assert render_index(conversations, memories, projects, frames, accounts) == snapshot


def test_snapshot_of_the_readme(snapshot: SnapshotAssertion) -> None:
    assert (
        render_readme(
            source="mi-export",
            format_version="batched-manifest",
            counts={"conversations": 4, "memories": 6},
            export_created_at="2026-09-18T16:59:47Z",
            missing_categories=["frames", "projects"],
        )
        == snapshot
    )
