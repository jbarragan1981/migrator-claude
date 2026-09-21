"""Parser de `memories` (spec 03, sección `memories` CA-1..CA-5 y comunes CA-C1..CA-C5).

Un test por regla. Los fixtures son sintéticos (contenido inventado); el fixture real
anonimizado de `v2026-batched/` solo se usa para comprobar que el parser no se rompe con
la FORMA del export real, nunca para verificar contenido (está anonimizado a `<str:N>`).
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from claude_export_md.adapters.parsers import memories as parser
from claude_export_md.adapters.source_folder import FolderSource
from claude_export_md.domain.entities import (
    CONVERSATIONS_MEMORY_PATH,
    ORIGIN_CONVERSATIONS_MEMORY,
    ORIGIN_MEMORY_FILES,
    ORIGIN_PROJECT_MEMORIES,
    Memory,
    Report,
    project_memory_path,
)

REAL_FIXTURE = Path(__file__).parent / "fixtures" / "v2026-batched" / "memories" / "memories.json"
ACCOUNT = "11111111-2222-4333-8444-555555555555"
PROJECT_1 = "ffffffff-0000-4000-8000-000000000001"
PROJECT_2 = "ffffffff-0000-4000-8000-000000000002"


# ------------------------------------------------------------------ utilidades


def parse_folder(root: Path) -> tuple[list[Memory], Report]:
    report = Report()
    return list(parser.parse(FolderSource(root), report)), report


def write_memories_json(root: Path, payload: dict[str, Any], part: int = 0) -> Path:
    """Escribe un `memories-<part>/memories/<uuid>.json` sintético dentro de `root`."""
    directory = root / f"memories-{part:03d}" / "memories"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ACCOUNT}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def by_path(memories: list[Memory]) -> dict[str, Memory]:
    return {memory.path: memory for memory in memories}


# ------------------------------------------------------- CA-1 un solo archivo


def test_ca1_reads_the_single_json_of_the_account(fixtures_dir: Path) -> None:
    """CA-1: un único JSON por cuenta; no se recorre una carpeta buscando .md."""
    memories, report = parse_folder(fixtures_dir / "memories-batched")

    # 3 memory_files + 1 conversations_memory + 2 project_memories
    assert len(memories) == 6
    assert report.errors == []
    assert report.counts == {"memories": 6}


# ------------------------------------------------- CA-2 memory_files con ruta


def test_ca2_memory_files_keep_their_real_path_and_content(fixtures_dir: Path) -> None:
    """CA-2: `path` y `content` salen tal cual del export."""
    memories, _ = parse_folder(fixtures_dir / "memories-batched")
    profile = by_path(memories)["/profile.md"]

    assert profile.content.startswith("# Perfil\n")
    assert profile.updated_at == datetime(2026, 1, 15, 9, 30, tzinfo=UTC)
    assert profile.project_id is None
    assert (profile.model_extra or {})["origin"] == ORIGIN_MEMORY_FILES


def test_memory_file_dates_are_normalised_to_utc(fixtures_dir: Path) -> None:
    """Spec 02: la fecha con offset +02:00 se guarda en UTC."""
    memories, _ = parse_folder(fixtures_dir / "memories-batched")

    assert by_path(memories)["/people/Ana Maria.md"].updated_at == datetime(
        2026, 2, 1, 16, 5, 42, tzinfo=UTC
    )


def test_unreadable_date_does_not_invalidate_the_memory(fixtures_dir: Path) -> None:
    """Spec 02 CA-6: fecha ilegible → `updated_at=None` y el valor original en `extra`."""
    memories, report = parse_folder(fixtures_dir / "memories-batched")
    area = by_path(memories)["/areas/Analisis Ñandú.md"]

    assert area.updated_at is None
    assert (area.model_extra or {})["updated_at_raw"] == "sin fecha"
    assert report.errors == []


# --------------------------------------------- CA-3 conversations_memory


def test_ca3_conversations_memory_gets_the_synthetic_path(fixtures_dir: Path) -> None:
    """CA-3 + ADR-0005: sin ruta propia → ruta sintética marcada en `extra`."""
    memories, _ = parse_folder(fixtures_dir / "memories-batched")
    memory = by_path(memories)[CONVERSATIONS_MEMORY_PATH]

    assert memory.content.startswith("# Lo que recuerdo")
    assert memory.project_id is None
    assert (memory.model_extra or {})["origin"] == ORIGIN_CONVERSATIONS_MEMORY
    assert (memory.model_extra or {})["synthetic_path"] is True


def test_empty_conversations_memory_produces_no_memory(tmp_path: Path) -> None:
    """Una cadena vacía no tiene nada que conservar: no genera archivo ni error."""
    write_memories_json(tmp_path, {"account_uuid": ACCOUNT, "conversations_memory": ""})
    memories, report = parse_folder(tmp_path)

    assert memories == []
    assert report.errors == []


def test_conversations_memory_of_unexpected_type_is_reported(tmp_path: Path) -> None:
    """CA-C2: un tipo inesperado se registra, no se descarta en silencio."""
    write_memories_json(tmp_path, {"account_uuid": ACCOUNT, "conversations_memory": {"a": 1}})
    memories, report = parse_folder(tmp_path)

    assert memories == []
    assert [error.item_id for error in report.errors] == ["conversations_memory"]


# ------------------------------------------------- CA-4 project_memories


def test_ca4_project_memories_link_to_their_project(fixtures_dir: Path) -> None:
    """CA-4: cada clave de `project_memories` queda ligada al proyecto por uuid."""
    memories, _ = parse_folder(fixtures_dir / "memories-batched")
    memory = by_path(memories)[project_memory_path(PROJECT_1)]

    assert memory.project_id == PROJECT_1
    assert memory.content.startswith("Memoria del primer proyecto")
    assert (memory.model_extra or {})["origin"] == ORIGIN_PROJECT_MEMORIES
    assert (memory.model_extra or {})["synthetic_path"] is True


def test_project_memories_are_emitted_sorted_by_uuid(fixtures_dir: Path) -> None:
    """CA-C5: el orden de un dict del JSON no manda; se ordena por uuid."""
    memories, _ = parse_folder(fixtures_dir / "memories-batched")
    project_ids = [memory.project_id for memory in memories if memory.project_id]

    assert project_ids == [PROJECT_1, PROJECT_2]


def test_project_memory_of_unexpected_type_is_reported(tmp_path: Path) -> None:
    """CA-C2: un valor que no es texto se registra con el uuid del proyecto."""
    write_memories_json(tmp_path, {"project_memories": {PROJECT_1: 42}})
    memories, report = parse_folder(tmp_path)

    assert memories == []
    assert [(error.item_id, error.category) for error in report.errors] == [(PROJECT_1, "memories")]


def test_project_memories_that_is_not_an_object_is_reported(tmp_path: Path) -> None:
    write_memories_json(tmp_path, {"project_memories": [PROJECT_1]})
    memories, report = parse_folder(tmp_path)

    assert memories == []
    assert [error.item_id for error in report.errors] == ["project_memories"]


def test_empty_project_memory_produces_no_memory(tmp_path: Path) -> None:
    """Un proyecto con memoria vacía no genera un archivo vacío ni un error."""
    write_memories_json(tmp_path, {"project_memories": {PROJECT_1: "", PROJECT_2: "algo"}})
    memories, report = parse_folder(tmp_path)

    assert [memory.project_id for memory in memories] == [PROJECT_2]
    assert report.errors == []


# ------------------------------------------- CA-5 colecciones vacías/ausentes


def test_ca5_empty_collections_are_tolerated(tmp_path: Path) -> None:
    """CA-5: `memory_files: []` y `project_memories: {}` no son un error."""
    write_memories_json(
        tmp_path,
        {"account_uuid": ACCOUNT, "memory_files": [], "project_memories": {}},
    )
    memories, report = parse_folder(tmp_path)

    assert memories == []
    assert report.errors == []
    assert report.counts == {}


def test_ca5_missing_collections_are_tolerated(tmp_path: Path) -> None:
    """CA-5: un export sin `memory_files` ni `project_memories` tampoco rompe."""
    write_memories_json(tmp_path, {"account_uuid": ACCOUNT})
    memories, report = parse_folder(tmp_path)

    assert memories == []
    assert report.errors == []


def test_collection_of_wrong_type_is_reported(tmp_path: Path) -> None:
    """Si `memory_files` no es una lista, se registra y se sigue con el resto."""
    write_memories_json(
        tmp_path,
        {"memory_files": "nada", "conversations_memory": "sigo aquí"},
    )
    memories, report = parse_folder(tmp_path)

    assert [memory.path for memory in memories] == [CONVERSATIONS_MEMORY_PATH]
    assert [error.item_id for error in report.errors] == ["memory_files"]


# ----------------------------------------------------- CA-C2 ítems corruptos


def test_cac2_broken_json_is_reported_and_the_run_continues(tmp_path: Path) -> None:
    """CA-C2: un archivo ilegible va a `Report.errors`; las otras partes se parsean."""
    (tmp_path / "memories-000" / "memories").mkdir(parents=True)
    (tmp_path / "memories-000" / "memories" / f"{ACCOUNT}.json").write_text(
        '{"memory_files": [', encoding="utf-8"
    )
    write_memories_json(tmp_path, {"conversations_memory": "sobrevivo"}, part=1)

    memories, report = parse_folder(tmp_path)

    assert [memory.path for memory in memories] == [CONVERSATIONS_MEMORY_PATH]
    assert len(report.errors) == 1
    assert report.errors[0].source_file is not None
    assert "memories-000" in report.errors[0].source_file


def test_root_that_is_not_an_object_is_reported(tmp_path: Path) -> None:
    """La raíz de este JSON es un objeto; un array es un formato que no entendemos."""
    directory = tmp_path / "memories-000" / "memories"
    directory.mkdir(parents=True)
    (directory / f"{ACCOUNT}.json").write_text("[1, 2, 3]", encoding="utf-8")

    memories, report = parse_folder(tmp_path)

    assert memories == []
    assert len(report.errors) == 1


def test_memory_file_entry_without_path_is_reported(tmp_path: Path) -> None:
    """Sin `path` no hay identificador (ADR-0005): se registra en vez de inventarlo."""
    write_memories_json(
        tmp_path,
        {"memory_files": [{"content": "huérfana"}, {"path": "/ok.md", "content": "ok"}]},
    )
    memories, report = parse_folder(tmp_path)

    assert [memory.path for memory in memories] == ["/ok.md"]
    assert [error.item_id for error in report.errors] == ["memory_files[0]"]


def test_memory_file_entry_that_is_not_an_object_is_reported(tmp_path: Path) -> None:
    write_memories_json(tmp_path, {"memory_files": ["no soy un objeto"]})
    memories, report = parse_folder(tmp_path)

    assert memories == []
    assert [error.item_id for error in report.errors] == ["memory_files[0]"]


# --------------------------------------------------------- CA-C1 multi-parte


def test_cac1_parts_are_concatenated_without_duplicating(tmp_path: Path) -> None:
    """CA-C1: varias partes se concatenan en orden y la ruta repetida no se duplica."""
    write_memories_json(
        tmp_path,
        {"memory_files": [{"path": "/profile.md", "content": "primera"}]},
        part=0,
    )
    write_memories_json(
        tmp_path,
        {
            "memory_files": [
                {"path": "/profile.md", "content": "repetida"},
                {"path": "/people/ana.md", "content": "nueva"},
            ]
        },
        part=1,
    )
    memories, report = parse_folder(tmp_path)

    assert [memory.path for memory in memories] == ["/profile.md", "/people/ana.md"]
    assert by_path(memories)["/profile.md"].content == "primera"
    assert any("/profile.md" in warning for warning in report.warnings)


# ------------------------------------------------ CA-C4 campos desconocidos


def test_cac4_unknown_fields_are_preserved(fixtures_dir: Path) -> None:
    """CA-C4: `confidence` no está en el modelo y sobrevive en `extra`."""
    memories, _ = parse_folder(fixtures_dir / "memories-batched")

    assert (by_path(memories)["/profile.md"].model_extra or {})["confidence"] == "alta"


def test_every_memory_records_the_file_it_came_from(fixtures_dir: Path) -> None:
    """`source_file` del frontmatter (spec 04) lo pone el parser, que es quien lo sabe."""
    memories, _ = parse_folder(fixtures_dir / "memories-batched")

    sources = {(memory.model_extra or {}).get("source_file") for memory in memories}
    assert sources == {f"memories-000/memories/{ACCOUNT}.json"}


# ----------------------------------------------------------- CA-C5 determinismo


def test_cac5_two_runs_produce_the_same_order(fixtures_dir: Path) -> None:
    first, _ = parse_folder(fixtures_dir / "memories-batched")
    second, _ = parse_folder(fixtures_dir / "memories-batched")

    assert [memory.path for memory in first] == [memory.path for memory in second]


def test_memory_files_come_before_the_synthetic_ones(fixtures_dir: Path) -> None:
    """Orden estable y legible: primero las del export, luego las sintéticas."""
    memories, _ = parse_folder(fixtures_dir / "memories-batched")

    assert [memory.path for memory in memories] == [
        "/profile.md",
        "/people/Ana Maria.md",
        "/areas/Analisis Ñandú.md",
        CONVERSATIONS_MEMORY_PATH,
        project_memory_path(PROJECT_1),
        project_memory_path(PROJECT_2),
    ]


# ------------------------------------------------------------- otros archivos


def test_non_json_files_in_the_category_are_warned_not_ignored(tmp_path: Path) -> None:
    """La hipótesis de la carpeta de .md quedó descartada; si aparece, se avisa."""
    write_memories_json(tmp_path, {"conversations_memory": "hola"})
    (tmp_path / "memories-000" / "profile.md").write_text("# Perfil\n", encoding="utf-8")

    memories, report = parse_folder(tmp_path)

    assert len(memories) == 1
    assert any("profile.md" in warning for warning in report.warnings)


def test_export_without_memories_category_yields_nothing(fixtures_dir: Path) -> None:
    """Sin categoría `memories` no hay memorias ni errores: no todas las cuentas tienen."""
    memories, report = parse_folder(fixtures_dir / "legacy-single")

    assert memories == []
    assert report.errors == []


def test_oversized_file_is_reported_instead_of_loaded(tmp_path: Path) -> None:
    """CA-C3: nunca un `json.load` de un archivo grande; si lo fuera, se registra."""
    write_memories_json(tmp_path, {"conversations_memory": "x" * 64})
    memories, report = parse_folder(tmp_path)  # control: cabe de sobra
    assert len(memories) == 1 and report.errors == []

    original = parser.MAX_JSON_BYTES
    try:
        parser.MAX_JSON_BYTES = 1
        memories, report = parse_folder(tmp_path)
    finally:
        parser.MAX_JSON_BYTES = original

    assert memories == []
    assert len(report.errors) == 1
    assert "bytes" in report.errors[0].reason


# ------------------------------------------- fixture real (solo estructura)


def test_real_anonymised_fixture_parses_without_errors(tmp_path: Path) -> None:
    """La FORMA del export real no rompe el parser (contenido anonimizado a `<str:N>`).

    Dos de las tres entradas de `memory_files` comparten `path` (`"<str:39>"`) porque el
    anonimizador reemplaza cada cadena por su longitud: por eso el parser conserva una
    sola de ellas y avisa de la repetida. Es un artefacto del fixture, no del export real.
    """
    directory = tmp_path / "memories-000" / "memories"
    directory.mkdir(parents=True)
    shutil.copy(REAL_FIXTURE, directory / f"{ACCOUNT}.json")

    memories, report = parse_folder(tmp_path)

    assert report.errors == []
    # 2 rutas distintas de memory_files (3 entradas, 2 con el mismo `<str:39>`)
    # + 1 conversations_memory + 16 project_memories
    assert len(memories) == 19
    assert len([m for m in memories if m.project_id]) == 16
    assert len(report.warnings) == 1
