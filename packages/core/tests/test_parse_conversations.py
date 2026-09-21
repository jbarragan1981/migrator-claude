"""Parser de `conversations` (spec 03, sección `conversations`: CA-1..CA-5 y CA-C1..C5).

Los fixtures son sintéticos (`fixtures/synthetic/conversations-batched/`): contenido
inventado, pero con la MISMA forma que confirmó la Fase 0 en
`docs/export-format/conversations.md` (los 4 tipos de bloque, `project_uuid` nullable,
`name`/`summary` vacíos, bloques de tipo desconocido).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from conftest import CountingSource, make_big_array

from claude_export_md.adapters.parsers import conversations as parser
from claude_export_md.adapters.source_folder import FolderSource
from claude_export_md.domain.entities import (
    BLOCK_TEXT,
    BLOCK_THINKING,
    BLOCK_TOOL_RESULT,
    BLOCK_TOOL_USE,
    Conversation,
    Report,
)

PROJECT = "ffffffff-0000-4000-8000-000000000001"
CONV_1 = "a1a1a1a1-1111-4000-8000-000000000001"
CONV_2 = "b2b2b2b2-2222-4000-8000-000000000002"
CONV_3 = "c3c3c3c3-3333-4000-8000-000000000003"
CONV_4 = "d4d4d4d4-4444-4000-8000-000000000004"


@pytest.fixture
def report() -> Report:
    return Report()


@pytest.fixture
def parsed(fixtures_dir: Path, report: Report) -> list[Conversation]:
    source = FolderSource(fixtures_dir / "conversations-batched")
    return list(parser.parse(source, report))


@pytest.fixture
def by_id(parsed: list[Conversation]) -> dict[str, Conversation]:
    return {conversation.id: conversation for conversation in parsed}


def write_export(root: Path, items: Any, part: int = 0) -> Path:  # noqa: ANN401
    """Escribe un `conversations-00N/conversations.json` sintético."""
    directory = root / f"conversations-{part:03d}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "conversations.json"
    path.write_text(
        items if isinstance(items, str) else json.dumps(items, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


# ------------------------------------------------- CA-1 bloques y su orden


def test_ca1_mixed_block_types_keep_their_order(by_id: dict[str, Conversation]) -> None:
    """CA-1: los 4 tipos observados llegan como bloques distintos y en el mismo orden."""
    message = by_id[CONV_1].messages[1]

    assert [block.type for block in message.blocks] == [
        BLOCK_THINKING,
        BLOCK_TOOL_USE,
        BLOCK_TOOL_RESULT,
        BLOCK_TEXT,
    ]


def test_ca1_an_unknown_block_type_is_kept_as_is(by_id: dict[str, Conversation]) -> None:
    """Un tipo que no conocemos no se descarta ni se renombra (CLAUDE.md §1.3)."""
    block = by_id[CONV_2].messages[1].blocks[1]

    assert block.type == "vision_preview"
    assert block.payload["caption"] == "Un bloque de un tipo que todavia no conocemos"
    assert block.payload["payload_version"] == 3


def test_messages_keep_sender_and_dates(by_id: dict[str, Conversation]) -> None:
    message = by_id[CONV_1].messages[0]

    assert message.id == "bbbbbbbb-0000-4000-8000-000000000001"
    assert message.sender == "human"
    assert message.created_at == datetime(2026, 1, 15, 14, 32, 5, 123456, tzinfo=UTC)


def test_message_text_is_derived_from_blocks_when_the_export_brings_none(
    by_id: dict[str, Conversation],
) -> None:
    """Spec 02 CA-2: el `text` vacío del export se reconstruye desde los bloques."""
    message = by_id[CONV_2].messages[0]

    assert message.text == "Segui con el plan del proyecto, por favor."


def test_parent_message_uuid_is_preserved_in_extra(by_id: dict[str, Conversation]) -> None:
    """El hilo (`parent_message_uuid`) no está en el modelo pero no se pierde."""
    extra = by_id[CONV_1].messages[0].model_extra or {}

    assert extra["parent_message_uuid"] == "00000000-0000-4000-8000-000000000000"


# ------------------------------------------------------- CA-2 enlace a proyecto


def test_ca2_project_uuid_links_the_conversation(by_id: dict[str, Conversation]) -> None:
    """CA-2: `project_uuid` no-null → `Conversation.project_id`."""
    assert by_id[CONV_2].project_id == PROJECT


def test_ca2_null_project_uuid_leaves_no_link(by_id: dict[str, Conversation]) -> None:
    assert by_id[CONV_1].project_id is None


def test_ca2_blank_project_uuid_is_not_a_link(tmp_path: Path, report: Report) -> None:
    """Una cadena vacía no es un uuid de proyecto: no se enlaza a `Project`."""
    write_export(tmp_path, [{"uuid": "x", "project_uuid": "   ", "chat_messages": []}])

    parsed = list(parser.parse(FolderSource(tmp_path), report))

    assert parsed[0].project_id is None


# --------------------------------------------- CA-3 payloads de esquema libre


def test_ca3_tool_use_input_is_preserved_whole(by_id: dict[str, Conversation]) -> None:
    """CA-3: `input` depende de la tool; se guarda entero, sin asumir claves."""
    block = by_id[CONV_1].messages[1].blocks[1]

    assert block.payload["input"] == {
        "description": "Leer el script de ventas",
        "path": "/home/usuaria/proyecto/scripts/ventas.py",
    }
    assert block.payload["display_content"] == {"text": "Leyendo scripts/ventas.py", "type": "text"}
    assert block.payload["name"] == "read_file"


def test_ca3_tool_result_keeps_its_nested_content_and_meta(
    by_id: dict[str, Conversation],
) -> None:
    """CA-3: el `content[]` anidado y `meta` del resultado llegan tal cual."""
    block = by_id[CONV_1].messages[1].blocks[2]

    assert block.payload["meta"] == {"output_format_category": "txt"}
    assert block.payload["tool_use_id"] == "toolu_0000000000000001"
    assert block.payload["content"][0]["type"] == "text"
    assert block.payload["is_error"] is False


def test_thinking_keeps_its_summaries(by_id: dict[str, Conversation]) -> None:
    block = by_id[CONV_1].messages[1].blocks[0]

    assert [item["summary"] for item in block.payload["summaries"]] == [
        "Revisar el script antes de responder",
        "Buscar el recalculo dentro del bucle",
    ]


# ------------------------------------------- CA-4 cadena vacía ≠ campo ausente


def test_ca4_empty_name_and_summary_are_not_treated_as_absent(
    by_id: dict[str, Conversation],
) -> None:
    """CA-4: `""` es un valor, no un campo que falta."""
    conversation = by_id[CONV_2]

    assert conversation.title == ""
    assert conversation.summary == ""


def test_a_null_summary_stays_none(by_id: dict[str, Conversation]) -> None:
    """`null` sí es ausencia, y se distingue de `""`."""
    assert by_id[CONV_3].summary is None


# ------------------------------------------------------------- fechas en UTC


def test_dates_are_normalised_to_utc(by_id: dict[str, Conversation]) -> None:
    """CLAUDE.md §1.4: todo en UTC, venga con el desplazamiento que venga."""
    assert by_id[CONV_2].created_at == datetime(2026, 2, 3, 6, 5, tzinfo=UTC)


def test_a_conversation_without_dates_is_still_parsed(by_id: dict[str, Conversation]) -> None:
    conversation = by_id[CONV_3]

    assert conversation.created_at is None
    assert conversation.title == "Charla sin fecha"


# ------------------------------------------------------ CA-C2 ítems corruptos


def test_cac2_an_item_that_is_not_an_object_is_reported_and_the_run_continues(
    parsed: list[Conversation], report: Report
) -> None:
    """CA-C2: el ítem se registra y el iterador sigue con los siguientes."""
    reasons = [error.reason for error in report.errors]

    assert any("se esperaba un objeto" in reason for reason in reasons)
    assert CONV_4 in {conversation.id for conversation in parsed}


def test_cac2_an_item_without_uuid_is_reported(report: Report, parsed: list[Conversation]) -> None:
    """Sin identificador no hay entidad: se registra con su posición en el array."""
    errors = [error for error in report.errors if error.reason.startswith("conversación sin")]

    assert len(errors) == 1
    assert errors[0].item_id == "item[4]"
    assert len(parsed) == 4


def test_cac2_chat_messages_with_the_wrong_shape_keeps_the_conversation(
    by_id: dict[str, Conversation], report: Report
) -> None:
    """Los mensajes ilegibles no tiran la conversación: título y fechas siguen siendo útiles."""
    assert by_id[CONV_4].messages == []
    assert any(error.item_id == CONV_4 for error in report.errors)


def test_cac2_broken_json_reports_the_file_and_keeps_what_ya_se_habia_leido(
    tmp_path: Path, report: Report
) -> None:
    """Un JSON truncado no lanza: se conserva lo leído y se registra el archivo."""
    write_export(tmp_path, '[{"uuid": "a", "chat_messages": []}, {"uuid": "b",')

    parsed = list(parser.parse(FolderSource(tmp_path), report))

    assert [conversation.id for conversation in parsed] == ["a"]
    assert any("JSON ilegible" in error.reason for error in report.errors)


def test_a_root_that_is_not_an_array_is_reported(tmp_path: Path, report: Report) -> None:
    """La raíz confirmada es un array; un objeto se avisa en vez de devolver cero en silencio."""
    write_export(tmp_path, {"conversations": []})

    parsed = list(parser.parse(FolderSource(tmp_path), report))

    assert parsed == []
    assert any("se esperaba un array" in error.reason for error in report.errors)


def test_a_file_that_disappears_between_el_inventario_y_la_lectura_se_reporta(
    tmp_path: Path, report: Report
) -> None:
    """El export se descubre antes de leerse: si desaparece en medio, no se lanza."""
    path = write_export(tmp_path, [{"uuid": "a", "chat_messages": []}])
    source = FolderSource(tmp_path)
    path.unlink()

    assert list(parser.parse(source, report)) == []
    assert any("no se pudo abrir" in error.reason for error in report.errors)


def test_an_empty_file_is_reported(tmp_path: Path, report: Report) -> None:
    write_export(tmp_path, "")

    assert list(parser.parse(FolderSource(tmp_path), report)) == []
    assert report.errors


def test_a_block_that_is_not_an_object_is_skipped_with_a_warning(
    by_id: dict[str, Conversation], report: Report
) -> None:
    """Un bloque con forma inesperada no invalida el mensaje que lo contiene."""
    message = by_id[CONV_3].messages[1]

    assert [block.type for block in message.blocks] == [BLOCK_TEXT]
    assert any("bloque" in warning for warning in report.warnings)


def test_a_message_without_uuid_gets_a_deterministic_synthetic_id(
    by_id: dict[str, Conversation], report: Report
) -> None:
    """Perder el texto por un uuid ausente sería peor: se le da un id derivado y se avisa."""
    message = by_id[CONV_3].messages[1]

    assert message.id == f"{CONV_3}#1"
    assert (message.model_extra or {})["synthetic_id"] is True
    assert any("sin uuid" in warning for warning in report.warnings)


def test_a_conversation_without_chat_messages_is_parsed_empty(
    tmp_path: Path, report: Report
) -> None:
    """Que falte la clave no es un error: la conversación existe, sin turnos."""
    write_export(tmp_path, [{"uuid": "a", "name": "Vacía"}])

    parsed = list(parser.parse(FolderSource(tmp_path), report))

    assert parsed[0].messages == []
    assert report.errors == []


def test_a_message_with_content_of_the_wrong_shape_keeps_its_text(
    tmp_path: Path, report: Report
) -> None:
    write_export(
        tmp_path, [{"uuid": "a", "chat_messages": [{"uuid": "m", "text": "hola", "content": 7}]}]
    )

    parsed = list(parser.parse(FolderSource(tmp_path), report))

    assert parsed[0].messages[0].blocks == []
    assert parsed[0].messages[0].text == "hola"


def test_a_file_of_the_category_that_is_not_json_is_skipped_with_a_warning(
    tmp_path: Path, report: Report
) -> None:
    """En este formato las conversaciones viajan en JSON; lo demás se avisa."""
    write_export(tmp_path, [{"uuid": "a", "chat_messages": []}])
    (tmp_path / "conversations-000" / "leeme.md").write_text("hola", encoding="utf-8")

    parsed = list(parser.parse(FolderSource(tmp_path), report))

    assert [conversation.id for conversation in parsed] == ["a"]
    assert any("no es JSON" in warning for warning in report.warnings)


def test_attachments_are_preserved_when_the_export_brings_them(
    tmp_path: Path, report: Report
) -> None:
    """La Fase 0 no los observó (spec 03); si aparecen, no se descartan."""
    write_export(
        tmp_path,
        [
            {
                "uuid": "a",
                "chat_messages": [
                    {"uuid": "m", "attachments": [{"file_name": "notas.txt"}, "suelto"]}
                ],
            }
        ],
    )

    parsed = list(parser.parse(FolderSource(tmp_path), report))

    assert parsed[0].messages[0].attachments == [{"file_name": "notas.txt"}]


def test_a_message_that_is_not_an_object_is_reported(tmp_path: Path, report: Report) -> None:
    write_export(tmp_path, [{"uuid": "a", "chat_messages": ["texto suelto"]}])

    parsed = list(parser.parse(FolderSource(tmp_path), report))

    assert parsed[0].messages == []
    assert any(error.item_id == "a#0" for error in report.errors)


# ------------------------------------------- CA-C1 partes y CA-C4 desconocidos


def test_cac1_parts_are_concatenated_without_duplicating(tmp_path: Path, report: Report) -> None:
    """CA-C1: `part 0..n` se concatenan en orden y un uuid repetido no se emite dos veces."""
    write_export(tmp_path, [{"uuid": "a", "chat_messages": []}], part=0)
    write_export(
        tmp_path,
        [{"uuid": "a", "chat_messages": []}, {"uuid": "b", "chat_messages": []}],
        part=1,
    )

    parsed = list(parser.parse(FolderSource(tmp_path), report))

    assert [conversation.id for conversation in parsed] == ["a", "b"]
    assert any("repetida" in warning for warning in report.warnings)


def test_cac4_unknown_fields_are_preserved(by_id: dict[str, Conversation]) -> None:
    """CA-C4: `account` no está en el modelo y aun así llega entero a `extra`."""
    extra = by_id[CONV_1].model_extra or {}

    assert extra["account"] == {"uuid": "11111111-2222-4333-8444-555555555555"}


def test_the_source_file_of_each_conversation_is_recorded(by_id: dict[str, Conversation]) -> None:
    """El frontmatter obligatorio pide `source_file` y el dominio no conoce el disco."""
    extra = by_id[CONV_1].model_extra or {}

    assert extra["source_file"] == "conversations-000/conversations.json"


def test_chat_messages_is_not_duplicated_inside_extra(by_id: dict[str, Conversation]) -> None:
    """`chat_messages` ya está en `messages`: repetirlo crudo duplicaría el export entero."""
    extra = by_id[CONV_1].model_extra or {}

    assert "chat_messages" not in extra
    assert "project_uuid" not in extra


def test_converted_conversations_are_counted(parsed: list[Conversation], report: Report) -> None:
    assert report.counts["conversations"] == len(parsed) == 4


# --------------------------------------------------------- CA-C3 streaming


def test_cac3_the_first_conversation_arrives_without_reading_the_whole_file(
    tmp_path: Path, report: Report
) -> None:
    """CA-C3: `json.load` habría leído los ~3 MB antes de devolver nada; `ijson` no."""
    root = tmp_path / "export"
    (root / "conversations-000").mkdir(parents=True)
    big = make_big_array(root / "conversations-000" / "conversations.json", items=20_000)
    assert big.stat().st_size > 3_000_000

    source = CountingSource(FolderSource(root))
    first = next(parser.parse(source, report))

    assert first.id.startswith("00000000")
    assert source.read_bytes[0] < 500_000


def test_cac3_a_file_over_the_limit_is_still_parsed(tmp_path: Path, report: Report) -> None:
    """A diferencia de `memories`, aquí NO hay techo de tamaño: se lee en streaming."""
    root = tmp_path / "export"
    (root / "conversations-000").mkdir(parents=True)
    make_big_array(root / "conversations-000" / "conversations.json", items=5_000)

    parsed = list(parser.parse(FolderSource(root), report))

    assert len(parsed) == 5_000
    assert report.errors == []


# ------------------------------------------------------- CA-C5 determinismo


def test_cac5_parse_sorted_orders_by_date_then_id(fixtures_dir: Path, report: Report) -> None:
    """CA-C5: orden de salida por `created_at`, luego `id`."""
    source = FolderSource(fixtures_dir / "conversations-batched")

    ordered = parser.parse_sorted(source, report)

    assert [conversation.id for conversation in ordered] == [CONV_1, CONV_2, CONV_4, CONV_3]


def test_cac5_conversations_without_date_go_last_and_keep_their_relative_order(
    tmp_path: Path, report: Report
) -> None:
    """Sin fecha no se puede ordenar por fecha: van al final, ordenadas por id."""
    write_export(
        tmp_path,
        [
            {"uuid": "z", "chat_messages": []},
            {"uuid": "a", "chat_messages": []},
            {"uuid": "m", "created_at": "2026-01-01T00:00:00Z", "chat_messages": []},
        ],
    )

    ordered = parser.parse_sorted(FolderSource(tmp_path), report)

    assert [conversation.id for conversation in ordered] == ["m", "a", "z"]


def test_cac5_two_runs_produce_the_same_order(fixtures_dir: Path) -> None:
    source = FolderSource(fixtures_dir / "conversations-batched")

    first = [c.id for c in parser.parse(source, Report())]
    second = [c.id for c in parser.parse(source, Report())]

    assert first == second


def test_parse_streams_and_does_not_materialise_the_collection(
    fixtures_dir: Path, report: Report
) -> None:
    """`parse` es un iterador perezoso: pedir uno no obliga a parsear los 291."""
    iterator = parser.parse(FolderSource(fixtures_dir / "conversations-batched"), report)

    first = next(iterator)

    assert first.id == CONV_1
    assert report.counts["conversations"] == 1
