"""Render del `_index.md` y del `README.md` (spec 04 CA-7, CLAUDE.md §5).

Módulo puro: aquí se prueba el TEXTO, sin tocar el disco. El árbol completo y su
determinismo se prueban en `test_convert.py`. El snapshot (`syrupy`) es la red de
seguridad del formato: si cambia una línea de la tabla, el diff lo enseña.
"""

from __future__ import annotations

from datetime import UTC, datetime

from syrupy.assertion import SnapshotAssertion

from claude_export_md.domain.entities import Conversation, conversations_memory, memory_from_file
from claude_export_md.rendering.index import (
    IndexEntry,
    conversation_entry,
    memory_entry,
    render_index,
    render_readme,
    sort_entries,
)


def at(day: int) -> datetime:
    return datetime(2026, 3, day, 9, 0, tzinfo=UTC)


ENTRIES = [
    IndexEntry(id="c", title="Tercera", path="conversations/2026/03/c.md", date=at(1)),
    IndexEntry(id="a", title="Primera", path="conversations/2026/03/a.md", date=at(3)),
    IndexEntry(id="b", title="Segunda", path="conversations/2026/03/b.md", date=at(2)),
    IndexEntry(id="z", title="Sin fecha", path="conversations/sin-fecha/z.md"),
]


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
    conversation = Conversation.model_validate(
        {
            "id": "a1a1a1a1-1111-4000-8000-000000000001",
            "title": "Análisis Ñandú / Q3",
            "created_at": "2026-01-15T14:32:05Z",
            "project_id": "ffffffff-0000-4000-8000-000000000001",
            "messages": [{"id": "m1", "sender": "human", "text": "hola"}],
        }
    )

    entry = conversation_entry(conversation)

    assert entry.path == "conversations/2026/01/2026-01-15_analisis-nandu-q3_a1a1a1a1.md"
    assert entry.message_count == 1
    assert entry.project_id == "ffffffff-0000-4000-8000-000000000001"


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
    memories = [memory_entry(conversations_memory("x"), "memories/conversations-memory.md")]

    assert render_index(ENTRIES, memories) == snapshot


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
