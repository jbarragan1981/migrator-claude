"""Tests del caso de uso `build_inventory` sobre carpetas ya extraídas (spec 01)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

from conftest import make_big_array, write_manifest

from claude_export_md import build_inventory, create_source, dumps_inventory
from claude_export_md.domain.redaction import UUID_MARK
from claude_export_md.ports.source import ExportSource, SourceFile
from claude_export_md.usecases.inventory import MAX_SHAPE_DEPTH, MAX_TOP_KEYS, shape

#: UUID inventado, con la forma del que Anthropic pone en el nombre del manifiesto.
ACCOUNT_UUID = "11111111-2222-3333-4444-555555555555"


def test_ca1_five_extracted_categories(fixtures_dir: Path) -> None:
    """CA-1: 5 carpetas extraídas → batched-manifest, 5 categorías con parts=[0]."""
    inventory = build_inventory(create_source(fixtures_dir / "batched-full"))

    assert inventory.format_version == "batched-manifest"
    assert sorted(inventory.categories) == [
        "conversations",
        "frames",
        "light_metadata",
        "memories",
        "projects",
    ]
    assert all(cat.parts == [0] for cat in inventory.categories.values())
    assert inventory.missing_categories == []
    assert inventory.missing_parts == {}


def test_root_is_only_the_folder_name(fixtures_dir: Path) -> None:
    """El inventario no filtra rutas absolutas (privacidad + estabilidad)."""
    inventory = build_inventory(create_source(fixtures_dir / "batched-full"))
    assert inventory.root == "batched-full"


def test_json_array_category_samples_keys(fixtures_dir: Path) -> None:
    conversations = build_inventory(create_source(fixtures_dir / "batched-full")).categories[
        "conversations"
    ]
    assert conversations.root_type == "array"
    file_inv = conversations.files[0]
    assert file_inv.path == "conversations-000/conversations.json"
    assert file_inv.part == 0
    assert file_inv.bytes > 0
    assert len(file_inv.item_shapes) == 2
    first = file_inv.item_shapes[0]
    assert isinstance(first, dict)
    assert first["uuid"] == "string"
    assert first["chat_messages"][0]["sender"] == "string"


def test_json_object_category_reports_top_keys(fixtures_dir: Path) -> None:
    light = build_inventory(create_source(fixtures_dir / "batched-full")).categories[
        "light_metadata"
    ]
    assert light.root_type == "object"
    assert light.files[0].top_keys == ["account", "settings", "exported_at"]
    assert light.files[0].item_shapes == []


def test_memories_folder_counts_markdown_files(fixtures_dir: Path) -> None:
    memories = build_inventory(create_source(fixtures_dir / "batched-full")).categories["memories"]
    assert memories.root_type == "markdown"
    assert memories.approx_item_count == 2
    assert memories.item_count_exact is True
    assert memories.file_count == 2
    # Nombres hoja colapsados en patrón + conteo (ADR-0004).
    assert [(f.pattern, f.count) for f in memories.files] == [
        ("memories-000/*.md", 1),
        ("memories-000/people/*.md", 1),
    ]
    assert all(f.path is None for f in memories.files)


def _memories_export(root: Path) -> Path:
    """Export sintético con memorias cuyo nombre de archivo revelaría una persona."""
    (root / "memories-000" / "people").mkdir(parents=True)
    (root / "memories-000" / "profile.md").write_text("# Perfil\n", encoding="utf-8")
    for name in ("ana-real", "bruno-real"):
        (root / "memories-000" / "people" / f"{name}.md").write_text("# x\n", encoding="utf-8")
    return root


def test_inventory_json_contains_no_leaf_filenames_for_markdown_categories(
    tmp_path: Path,
) -> None:
    """Bloqueante: `inventory.json` se comparte; nunca puede traer nombres de personas."""
    payload = dumps_inventory(build_inventory(create_source(_memories_export(tmp_path / "export"))))

    assert "ana-real" not in payload
    assert "bruno-real" not in payload
    assert "memories-000/people/*.md" in payload


def test_markdown_files_are_grouped_by_pattern_with_count(tmp_path: Path) -> None:
    memories = build_inventory(create_source(_memories_export(tmp_path / "export"))).categories[
        "memories"
    ]

    people = next(f for f in memories.files if f.pattern == "memories-000/people/*.md")
    assert people.count == 2
    assert people.bytes > 0
    assert people.root_type == "markdown"
    assert people.approx_item_count == 2
    assert memories.file_count == 3


def test_json_part_files_keep_their_literal_name(tmp_path: Path) -> None:
    """`conversations-001.json` no revela nada del usuario: se sigue listando tal cual."""
    root = tmp_path / "export"
    (root / "conversations-000").mkdir(parents=True)
    (root / "conversations-000" / "conversations-001.json").write_text("[]", encoding="utf-8")

    files = build_inventory(create_source(root)).categories["conversations"].files

    assert [f.path for f in files] == ["conversations-000/conversations-001.json"]
    assert files[0].pattern is None
    assert files[0].count == 1


def test_top_keys_that_look_like_uuid_or_email_are_masked(tmp_path: Path) -> None:
    root = tmp_path / "export"
    (root / "light_metadata-000").mkdir(parents=True)
    (root / "light_metadata-000" / "light_metadata.json").write_text(
        json.dumps(
            {
                "11111111-1111-4111-8111-111111111111": 1,
                "ana-real@example.com": 2,
                "settings": {"22222222-2222-4222-8222-222222222222": "x"},
            }
        ),
        encoding="utf-8",
    )

    payload = dumps_inventory(build_inventory(create_source(root)))
    file_inv = build_inventory(create_source(root)).categories["light_metadata"].files[0]

    assert file_inv.top_keys == ["<uuid>", "<email>", "settings"]
    assert "ana-real" not in payload
    assert "11111111-1111" not in payload


def test_shape_keys_that_look_like_uuid_are_masked(tmp_path: Path) -> None:
    root = tmp_path / "export"
    (root / "frames-000").mkdir(parents=True)
    (root / "frames-000" / "frames.json").write_text(
        json.dumps([{"by": {"33333333-3333-4333-8333-333333333333": "x"}}]), encoding="utf-8"
    )

    first = build_inventory(create_source(root)).categories["frames"].files[0].item_shapes[0]

    assert first == {"by": {"<uuid>": "string"}}


def test_warnings_never_contain_leaf_filenames(tmp_path: Path) -> None:
    root = tmp_path / "export"
    (root / "memories-000").mkdir(parents=True)
    (root / "memories-000" / "notas-de-ana-real.json").write_text("[{oops", encoding="utf-8")

    inventory = build_inventory(create_source(root))

    assert inventory.warnings
    assert "ana-real" not in dumps_inventory(inventory)
    assert any("memories-000/*.json" in warning for warning in inventory.warnings)


def _memories_only_export(root: Path) -> Path:
    (root / "memories-000").mkdir(parents=True)
    (root / "memories-000" / "profile.md").write_text("# Perfil\n", encoding="utf-8")
    return root


def test_unreadable_manifest_warning_redacts_the_account_uuid(tmp_path: Path) -> None:
    """El nombre real del manifiesto lleva el uuid de la cuenta: no puede entrar al JSON."""
    root = _memories_only_export(tmp_path / "export")
    (root / f"member-manifest-{ACCOUNT_UUID}-2026-02-01.json").write_text(
        "{not json", encoding="utf-8"
    )

    inventory = build_inventory(create_source(root))

    assert any("manifiesto" in warning.lower() for warning in inventory.warnings)
    assert any(UUID_MARK in warning for warning in inventory.warnings)
    assert ACCOUNT_UUID not in dumps_inventory(inventory)


def test_manifest_category_with_a_uuid_is_redacted(tmp_path: Path) -> None:
    """Las categorías salen del manifiesto: se redactan al usarlas (defensa en profundidad)."""
    root = _memories_only_export(tmp_path / "export")
    write_manifest(root, {f"notas-de-{ACCOUNT_UUID}": [0], "memories": [0]})

    inventory = build_inventory(create_source(root))

    assert f"notas-de-{UUID_MARK}" in inventory.missing_categories
    assert ACCOUNT_UUID not in dumps_inventory(inventory)


def test_ca2_missing_category_is_reported_not_raised(fixtures_dir: Path) -> None:
    """CA-2: falta frames-000 → missing_categories=['frames'] sin excepción."""
    inventory = build_inventory(create_source(fixtures_dir / "batched-missing-frames"))
    assert inventory.missing_categories == ["frames"]
    assert "frames" not in inventory.categories


def test_ca5_manifest_declares_missing_part(tmp_path: Path, fixtures_dir: Path) -> None:
    """CA-5: manifiesto declara conversations part 1 y solo existe part 0."""
    root = tmp_path / "export"
    shutil.copytree(fixtures_dir / "batched-full", root)
    write_manifest(
        root,
        {
            "conversations": [0, 1],
            "memories": [0],
            "projects": [0],
            "frames": [0],
            "light_metadata": [0],
        },
    )

    inventory = build_inventory(create_source(root))

    assert inventory.missing_parts == {"conversations": [1]}
    assert inventory.missing_categories == []
    assert inventory.manifest_path == "member-manifest-2026-02-01.json"


def test_manifest_declaring_unknown_category_is_missing(tmp_path: Path, fixtures_dir: Path) -> None:
    root = tmp_path / "export"
    shutil.copytree(fixtures_dir / "batched-missing-frames", root)
    write_manifest(root, {"conversations": [0], "frames": [0]})

    inventory = build_inventory(create_source(root))

    assert inventory.missing_categories == ["frames"]
    assert inventory.missing_parts == {}


def test_ca6_output_is_byte_identical_between_runs(fixtures_dir: Path) -> None:
    """CA-6: dos corridas sobre el mismo input producen el mismo JSON."""
    first = dumps_inventory(build_inventory(create_source(fixtures_dir / "batched-full")))
    second = dumps_inventory(build_inventory(create_source(fixtures_dir / "batched-full")))
    assert first == second
    payload = json.loads(first)
    assert "generated_at" not in payload
    assert first == json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def test_legacy_single_zip_layout_is_detected(fixtures_dir: Path) -> None:
    inventory = build_inventory(create_source(fixtures_dir / "legacy-single"))
    assert inventory.format_version == "legacy-single-zip"
    assert sorted(inventory.categories) == ["conversations", "projects", "users"]
    assert inventory.categories["conversations"].parts == [0]


def test_non_json_non_markdown_files_are_listed_but_not_parsed(tmp_path: Path) -> None:
    root = tmp_path / "export"
    (root / "frames-000").mkdir(parents=True)
    (root / "frames-000" / "captura.png").write_bytes(b"\x89PNG\r\n")

    file_inv = build_inventory(create_source(root)).categories["frames"].files[0]

    assert file_inv.root_type == "other"
    assert file_inv.item_shapes == []
    assert file_inv.error is None


def test_scalar_json_root_is_reported_as_unknown(tmp_path: Path) -> None:
    root = tmp_path / "export"
    (root / "frames-000").mkdir(parents=True)
    (root / "frames-000" / "frames.json").write_text('"solo un string"', encoding="utf-8")

    file_inv = build_inventory(create_source(root)).categories["frames"].files[0]

    assert file_inv.root_type == "unknown"
    assert file_inv.error is not None


def test_shape_reports_types_never_values() -> None:
    item = {"list": ["texto"], "n": 1.5, "ok": True, "x": None, "obj": {"k": "v"}}

    assert shape(item) == {
        "list": ["string"],
        "n": "number",
        "ok": "boolean",
        "x": "null",
        "obj": {"k": "string"},
    }


def test_shape_is_depth_limited() -> None:
    deep: dict[str, Any] = {"leaf": 1}
    for _ in range(MAX_SHAPE_DEPTH + 2):
        deep = {"nested": deep}

    result = shape(deep)

    for _ in range(MAX_SHAPE_DEPTH):
        assert isinstance(result, dict)
        result = result["nested"]
    assert result == "object"


def test_shape_reaches_message_content_blocks(fixtures_dir: Path) -> None:
    """El muestreo llega a `chat_messages[0].content[0]` (CLAUDE.md §4)."""
    inventory = build_inventory(create_source(fixtures_dir / "batched-full"))
    first = inventory.categories["conversations"].files[0].item_shapes[0]
    assert isinstance(first, dict)
    assert first["chat_messages"][0]["content"] == [{"type": "string", "text": "string"}]


def test_object_sampling_stops_at_max_top_keys(tmp_path: Path) -> None:
    root = tmp_path / "export"
    (root / "light_metadata-000").mkdir(parents=True)
    payload = {f"k{index:04d}": index for index in range(MAX_TOP_KEYS + 50)}
    (root / "light_metadata-000" / "light_metadata.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    file_inv = build_inventory(create_source(root)).categories["light_metadata"].files[0]

    assert len(file_inv.top_keys) == MAX_TOP_KEYS
    assert file_inv.truncated is True


def test_corrupt_json_is_reported_per_file_not_raised(tmp_path: Path) -> None:
    root = tmp_path / "export"
    (root / "conversations-000").mkdir(parents=True)
    (root / "conversations-000" / "conversations.json").write_text("[{oops", encoding="utf-8")

    inventory = build_inventory(create_source(root))

    file_inv = inventory.categories["conversations"].files[0]
    assert file_inv.error is not None
    assert inventory.warnings


class _CountingStream:
    def __init__(self, inner: IO[bytes], counter: list[int]) -> None:
        self._inner = inner
        self._counter = counter

    def read(self, size: int = -1) -> bytes:
        data = self._inner.read(size)
        self._counter[0] += len(data)
        return data

    def close(self) -> None:
        self._inner.close()


class _CountingSource:
    """Decorador de `ExportSource` que cuenta los bytes leídos (CA-3)."""

    def __init__(self, inner: ExportSource) -> None:
        self._inner = inner
        self.read_bytes = [0]

    @property
    def root(self) -> str:
        return self._inner.root

    @property
    def format_version(self) -> str:
        return self._inner.format_version

    def files(self) -> list[SourceFile]:
        return list(self._inner.files())

    def manifest(self) -> Any:
        return self._inner.manifest()

    @contextmanager
    def open_file(self, file: SourceFile) -> Iterator[IO[bytes]]:
        with self._inner.open_file(file) as fp:
            yield _CountingStream(fp, self.read_bytes)  # type: ignore[misc]


def test_ca3_sampling_does_not_grow_with_file_size(tmp_path: Path) -> None:
    """CA-3: de un array enorme se leen ≤ 3 ítems y una fracción mínima de bytes."""
    root = tmp_path / "export"
    (root / "conversations-000").mkdir(parents=True)
    big = make_big_array(root / "conversations-000" / "conversations.json", items=20_000)
    assert big.stat().st_size > 3_000_000

    source = _CountingSource(create_source(root))
    inventory = build_inventory(source)

    file_inv = inventory.categories["conversations"].files[0]
    assert len(file_inv.item_shapes) == 3
    assert source.read_bytes[0] < 500_000
    assert file_inv.approx_item_count is not None
    assert file_inv.approx_item_count > 10_000
    assert file_inv.item_count_exact is False
