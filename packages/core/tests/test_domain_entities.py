"""Entidades de dominio (spec 02 + lo confirmado por la Fase 0, ADR-0005).

Un test por regla: tolerancia a esquema (CA-1), texto derivado de los bloques (CA-2),
fechas naive asumidas UTC (CA-3), inmutabilidad y serialización (CA-4), y las tres
variantes de `Memory` que el export real obliga a representar.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from claude_export_md.domain.dates import parse_timestamp
from claude_export_md.domain.entities import (
    BLOCK_TEXT,
    BLOCK_THINKING,
    BLOCK_TOOL_RESULT,
    BLOCK_TOOL_USE,
    CONVERSATIONS_MEMORY_PATH,
    SENDER_HUMAN,
    Account,
    ContentBlock,
    Conversation,
    Frame,
    FrameVersion,
    Memory,
    Message,
    ParseError,
    Project,
    ProjectDoc,
    Report,
    conversations_memory,
    memory_from_file,
    project_memory,
    project_memory_path,
    text_from_blocks,
)

# ---------------------------------------------------------------- CA-1 esquema


def test_unknown_keys_are_kept_in_model_extra() -> None:
    """CA-1: nada se descarta en silencio; lo desconocido queda accesible."""
    conversation = Conversation.model_validate(
        {"id": "c1", "starred": True, "sanity_check": {"nested": 1}}
    )

    assert conversation.model_extra == {"starred": True, "sanity_check": {"nested": 1}}


def test_only_the_identifier_is_required() -> None:
    """Regla del spec 02: todo opcional salvo `id` (o `path` en Memory)."""
    assert Conversation(id="c1").title is None
    assert Memory(path="/profile.md").content == ""

    with pytest.raises(ValidationError):
        Conversation()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Memory()  # type: ignore[call-arg]


def test_empty_string_is_not_treated_as_a_missing_field() -> None:
    """spec 03 conversations CA-4 / projects CA-2: `""` es un valor, no una ausencia."""
    conversation = Conversation(id="c1", title="", summary="")
    project = Project(id="p1", instructions="")

    assert conversation.title == ""
    assert conversation.summary == ""
    assert project.instructions == ""


def test_content_block_keeps_the_whole_raw_block_in_payload() -> None:
    """spec 03 conversations CA-3: `input`/`display_content` son de esquema libre."""
    raw = {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "str_replace",
        "input": {"description": "d", "path": "/tmp/x"},
        "display_content": {"json_block": "{}", "type": "text"},
        "mcp_server_url": None,
    }

    block = ContentBlock.from_raw(raw)

    assert block.type == BLOCK_TOOL_USE
    assert block.payload == {k: v for k, v in raw.items() if k != "type"}


def test_content_block_without_type_falls_back_to_unknown() -> None:
    assert ContentBlock.from_raw({"text": "hola"}).type == "unknown"


# ------------------------------------------------------------------ CA-2 texto


def test_message_text_is_derived_from_its_text_blocks() -> None:
    """CA-2: sin `text`, dos bloques `text` se unen por una línea en blanco."""
    message = Message(
        id="m1",
        blocks=[
            ContentBlock(type=BLOCK_TEXT, payload={"text": "primero"}),
            ContentBlock(type=BLOCK_TEXT, payload={"text": "segundo"}),
        ],
    )

    assert message.text == "primero\n\nsegundo"


def test_message_text_ignores_non_text_blocks() -> None:
    """`thinking`, `tool_use` y `tool_result` no son el texto del mensaje."""
    message = Message(
        id="m1",
        blocks=[
            ContentBlock(type=BLOCK_THINKING, payload={"thinking": "razonando"}),
            ContentBlock(type=BLOCK_TEXT, payload={"text": "la respuesta"}),
            ContentBlock(type=BLOCK_TOOL_USE, payload={"name": "bash"}),
            ContentBlock(type=BLOCK_TOOL_RESULT, payload={"content": [{"text": "salida"}]}),
        ],
    )

    assert message.text == "la respuesta"


def test_message_keeps_its_own_text_when_the_export_brings_one() -> None:
    """El `text` plano del export manda; solo se deriva cuando falta."""
    message = Message(
        id="m1",
        text="el del export",
        blocks=[ContentBlock(type=BLOCK_TEXT, payload={"text": "el del bloque"})],
    )

    assert message.text == "el del export"


def test_message_text_is_derived_from_raw_blocks_too() -> None:
    """El parser puede pasar los bloques crudos de `content[]` sin construirlos antes."""
    message = Message.model_validate({"id": "m1", "blocks": [{"type": "text", "text": "crudo"}]})

    assert message.text == "crudo"
    assert message.blocks[0].payload == {"text": "crudo"}


def test_message_without_text_blocks_has_empty_text() -> None:
    message = Message(id="m1", blocks=[ContentBlock(type=BLOCK_THINKING, payload={})])

    assert message.text == ""


def test_text_from_blocks_is_a_pure_domain_function() -> None:
    blocks: list[ContentBlock | Mapping[str, Any]] = [
        ContentBlock(type=BLOCK_TEXT, payload={"text": "a"}),
        {"type": "text", "text": "b"},
    ]

    assert text_from_blocks(blocks) == "a\n\nb"


# ------------------------------------------------------------------ CA-3 fechas


def test_naive_timestamp_is_assumed_utc_and_flagged() -> None:
    """CA-3: `created_at` sin zona → UTC y `extra["tz_assumed"] = True`."""
    conversation = Conversation.model_validate({"id": "c1", "created_at": "2026-03-04T05:06:07"})

    assert conversation.created_at == datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    assert conversation.model_extra is not None
    assert conversation.model_extra["tz_assumed"] is True


def test_aware_timestamp_is_not_flagged() -> None:
    conversation = Conversation.model_validate({"id": "c1", "created_at": "2026-03-04T05:06:07Z"})

    assert conversation.created_at == datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    assert (conversation.model_extra or {}).get("tz_assumed") is None


def test_offset_timestamp_is_converted_to_utc_without_flag() -> None:
    conversation = Conversation.model_validate(
        {"id": "c1", "created_at": "2026-03-04T05:06:07+02:00"}
    )

    assert conversation.created_at == datetime(2026, 3, 4, 3, 6, 7, tzinfo=UTC)
    assert (conversation.model_extra or {}).get("tz_assumed") is None


def test_every_entity_with_dates_normalises_them() -> None:
    """La regla es del dominio entero, no solo de `Conversation`."""
    naive = "2026-03-04T05:06:07"
    entities = (
        Memory.model_validate({"path": "/profile.md", "updated_at": naive}),
        Message.model_validate({"id": "m1", "created_at": naive}),
        Frame.model_validate({"id": "f1", "updated_at": naive}),
    )

    for entity in entities:
        assert (entity.model_extra or {}).get("tz_assumed") is True


def test_unparseable_timestamp_does_not_break_the_entity() -> None:
    """Tolerancia: una fecha ilegible se conserva cruda en `extra`, no tumba el ítem."""
    conversation = Conversation.model_validate({"id": "c1", "created_at": "ayer por la tarde"})

    assert conversation.created_at is None
    assert (conversation.model_extra or {})["created_at_raw"] == "ayer por la tarde"


def test_a_non_mapping_input_is_rejected_by_pydantic_not_by_the_validator() -> None:
    """La normalización de fechas se aparta: quien reporta el tipo inválido es pydantic."""
    with pytest.raises(ValidationError):
        Conversation.model_validate("no soy un objeto")


@pytest.mark.parametrize(
    ("value", "expected", "assumed"),
    [
        ("2026-03-04T05:06:07Z", datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC), False),
        ("2026-03-04T05:06:07.123456Z", datetime(2026, 3, 4, 5, 6, 7, 123456, tzinfo=UTC), False),
        ("2026-03-04T05:06:07", datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC), True),
        (datetime(2026, 3, 4, 5, 6, 7), datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC), True),
        (
            datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone(timedelta(hours=-5))),
            datetime(2026, 3, 4, 10, 6, 7, tzinfo=UTC),
            False,
        ),
        ("", None, False),
        (None, None, False),
        (42, None, False),
    ],
)
def test_parse_timestamp_normalises_to_utc(
    value: object, expected: datetime | None, assumed: bool
) -> None:
    assert parse_timestamp(value) == (expected, assumed)


# ------------------------------------------- CA-4 inmutabilidad y serialización


def test_entities_are_frozen() -> None:
    conversation = Conversation(id="c1", title="uno")

    with pytest.raises(ValidationError):
        conversation.title = "otro"


def test_entities_without_collections_are_hashable() -> None:
    memory = Memory(path="/profile.md", content="x")

    assert len({memory, Memory(path="/profile.md", content="x")}) == 1


def test_model_dump_json_mode_is_json_serialisable() -> None:
    """CA-4: `model_dump(mode="json")` alimenta el frontmatter y `_report/`."""
    conversation = Conversation.model_validate(
        {
            "id": "c1",
            "title": "Título",
            "created_at": "2026-03-04T05:06:07Z",
            "project_id": "p1",
            "messages": [
                {
                    "id": "m1",
                    "sender": SENDER_HUMAN,
                    "created_at": "2026-03-04T05:06:07Z",
                    "blocks": [{"type": BLOCK_TEXT, "text": "hola"}],
                }
            ],
            "starred": True,
        }
    )

    dumped = conversation.model_dump(mode="json")

    assert json.dumps(dumped)  # no lanza
    assert dumped["created_at"] == "2026-03-04T05:06:07Z"
    assert dumped["messages"][0]["text"] == "hola"
    assert dumped["starred"] is True


# ------------------------------------------------- Memory: tres orígenes (ADR-0005)


def test_memory_from_file_keeps_the_real_path() -> None:
    """spec 03 memories CA-2: `path` y `content` salen de `memory_files[]`."""
    memory = memory_from_file(
        {"path": "/people/ana.md", "content": "notas", "updated_at": "2026-03-04T05:06:07Z"}
    )

    assert memory.path == "/people/ana.md"
    assert memory.content == "notas"
    assert memory.updated_at == datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    assert memory.project_id is None
    assert (memory.model_extra or {})["origin"] == "memory_files"
    assert "synthetic_path" not in (memory.model_extra or {})


def test_conversations_memory_gets_a_fixed_synthetic_path() -> None:
    """spec 03 memories CA-3: sin path propio → path sintético marcado en `extra`."""
    memory = conversations_memory("resumen de todo")

    assert memory.path == CONVERSATIONS_MEMORY_PATH
    assert memory.content == "resumen de todo"
    assert memory.project_id is None
    assert (memory.model_extra or {})["origin"] == "conversations_memory"
    assert (memory.model_extra or {})["synthetic_path"] is True


def test_project_memory_is_linked_to_its_project() -> None:
    """spec 03 memories CA-4: cada clave de `project_memories` enlaza a un Project."""
    memory = project_memory("11111111-1111-4111-8111-111111111111", "memoria del proyecto")

    assert memory.project_id == "11111111-1111-4111-8111-111111111111"
    assert memory.path == project_memory_path("11111111-1111-4111-8111-111111111111")
    assert (memory.model_extra or {})["origin"] == "project_memories"
    assert (memory.model_extra or {})["synthetic_path"] is True


def test_synthetic_paths_never_collide_with_a_real_memory_path() -> None:
    """Las rutas inventadas van bajo `_`; Anthropic no emite esa forma (ADR-0005)."""
    paths = {CONVERSATIONS_MEMORY_PATH, project_memory_path("u1")}

    assert all(path.startswith("/_") for path in paths)
    assert len(paths) == 2


def test_synthetic_paths_are_deterministic() -> None:
    assert project_memory_path("u1") == project_memory_path("u1")


# ------------------------------------------------- Resto de entidades (Fase 0)


def test_account_maps_the_light_metadata_item() -> None:
    """spec 03 light_metadata CA-1."""
    account = Account(id="u1", email="ana@example.com", display_name="Ana")

    assert account.settings == {}
    assert account.model_dump(mode="json")["email"] == "ana@example.com"


def test_project_doc_without_content_is_explicitly_unavailable() -> None:
    """spec 03 projects CA-3: `None` = no viene en el export; `""` = doc vacío."""
    doc = ProjectDoc(id="d1", filename="notas.md")

    assert doc.content is None
    assert ProjectDoc(id="d2", filename="vacio.md", content="").content == ""


def test_project_holds_docs_and_conversation_links() -> None:
    project = Project(
        id="p1",
        name="Proyecto",
        instructions="",
        creator_id="u1",
        docs=[ProjectDoc(id="d1", filename="notas.md")],
        conversation_ids=["c1", "c2"],
    )

    assert [doc.id for doc in project.docs] == ["d1"]
    assert project.conversation_ids == ["c1", "c2"]
    assert project.creator_id == "u1"


def test_frame_keeps_versions_and_the_raw_payload() -> None:
    """spec 03 frames CA-1/CA-2: el contenido real no viaja; se preserva el JSON."""
    raw: dict[str, Any] = {
        "id": "f1",
        "kind": "document",
        "visibility": "private",
        "owner_account": "u1",
        "updated_at": "2026-03-04T05:06:07Z",
        "active_version": "v2",
        "versions": [
            {"id": "v1", "title": "Uno", "created_at": "2026-03-01T00:00:00Z"},
            {"id": "v2", "title": "Dos", "created_at": "2026-03-04T00:00:00Z"},
        ],
    }

    frame = Frame.model_validate({**raw, "payload": raw})
    active = frame.active()

    assert [version.id for version in frame.versions] == ["v1", "v2"]
    assert active is not None
    assert active.title == "Dos"
    assert frame.payload == raw


def test_frame_without_active_version_has_no_active_one() -> None:
    assert Frame(id="f1", versions=[FrameVersion(id="v1")]).active() is None


def test_frame_with_an_unresolvable_active_version_returns_none() -> None:
    """spec 03 frames CA-3: no coincidir no es una excepción."""
    frame = Frame(id="f1", active_version="v9", versions=[FrameVersion(id="v1")])

    assert frame.active() is None


# ------------------------------------------------------------ Report / ParseError


def test_report_accumulates_errors_warnings_and_counts() -> None:
    """CLAUDE.md §4: un ítem ilegible no detiene la corrida, se acumula."""
    report = Report()

    report.add_error(category="conversations", item_id="c1", reason="json roto")
    report.add_warning("frames: contenido no disponible")
    report.count("conversations")
    report.count("conversations", 2)

    assert report.counts == {"conversations": 3}
    assert report.warnings == ["frames: contenido no disponible"]
    assert [error.item_id for error in report.errors] == ["c1"]


def test_parse_error_is_serialisable_for_errors_jsonl() -> None:
    """spec 04 CA-8: una línea JSON por `ParseError`."""
    error = ParseError(
        category="memories",
        item_id="/profile.md",
        reason="sin content",
        source_file="memories.json",
    )

    assert json.loads(json.dumps(error.model_dump(mode="json"))) == {
        "category": "memories",
        "item_id": "/profile.md",
        "reason": "sin content",
        "source_file": "memories.json",
    }
