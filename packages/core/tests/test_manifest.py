"""Tests del parseo tolerante de `member-manifest-*.json` (solo categorías y partes)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_export_md import build_inventory, create_source
from claude_export_md.adapters.manifest import find_manifest, parse_manifest
from claude_export_md.domain.manifest import split_part_suffix
from claude_export_md.errors import UnknownFormatError


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("conversations-000", ("conversations", 0)),
        ("conversations-000.zip", ("conversations", 0)),
        ("conversations-012", ("conversations", 12)),
        ("conversations-000000", ("conversations", 0)),  # 6 dígitos, cero a la izquierda
        ("light_metadata-000", ("light_metadata", 0)),
    ],
)
def test_split_part_suffix_accepts_real_part_numbers(name: str, expected: tuple[str, int]) -> None:
    assert split_part_suffix(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "data-2025-03-01",  # fecha, no parte: antes daba ("data-2025-03", 1)
        "claude-export-2026-02-01",
        "claude-export-2026",  # un año de 4 dígitos sin cero inicial no es una parte
        "conversations-1",  # las partes vienen con cero a la izquierda (`-000`)
        "conversations",
    ],
)
def test_split_part_suffix_ignores_names_without_a_part_number(name: str) -> None:
    assert split_part_suffix(name) is None


def _write(root: Path, payload: object) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "member-manifest-2026-02-01.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_find_manifest_returns_none_when_absent(tmp_path: Path) -> None:
    assert find_manifest(tmp_path) is None


def test_declared_parts_from_files_key(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {
            "files": [
                {"category": "conversations", "part": 0},
                {"category": "conversations", "part": 1},
                {"category": "memories", "part": 0},
            ]
        },
    )
    manifest = parse_manifest(path)
    assert manifest.declared_parts() == {"conversations": [0, 1], "memories": [0]}


def test_declared_parts_from_data_files_key(tmp_path: Path) -> None:
    """Forma REAL confirmada en Fase 0: la lista va bajo `data_files`.

    Ver `docs/export-format/manifest.md`.
    """
    path = _write(
        tmp_path,
        {
            "created_at": "2026-02-01T00:00:00Z",
            "version": "1.0",
            "instructions": "Descargue cada archivo",
            "total_files": 3,
            "data_files": [
                {
                    "category": "conversations",
                    "part": 0,
                    "batch_index": 0,
                    "filename": "conversations-000.zip",
                    "export_url": "https://example.com/one-time",
                },
                {
                    "category": "memories",
                    "part": 0,
                    "batch_index": 1,
                    "filename": "memories-000.zip",
                    "export_url": "https://example.com/one-time",
                },
                {
                    "category": "memories",
                    "part": 1,
                    "batch_index": 2,
                    "filename": "memories-001.zip",
                    "export_url": "https://example.com/one-time",
                },
            ],
        },
    )

    manifest = parse_manifest(path)

    assert manifest.declared_parts() == {"conversations": [0], "memories": [0, 1]}


def test_real_manifest_fixture_declares_its_entries() -> None:
    """El fixture del export real declara las 5 categorías, parte 0, con valores literales.

    `category`/`part`/`batch_index`/`filename` son esquema fijo de Anthropic (no datos del
    usuario), así que el fixture los conserva tal cual; lo único que se quita es `export_url`.
    """
    fixture = (
        Path(__file__).parent / "fixtures" / "v2026-batched" / "manifest" / "member-manifest.json"
    )

    manifest = parse_manifest(fixture)

    assert manifest.declared_parts() == {
        "conversations": [0],
        "frames": [0],
        "light_metadata": [0],
        "memories": [0],
        "projects": [0],
    }
    assert len(manifest.files) == len(json.loads(fixture.read_text(encoding="utf-8"))["data_files"])
    assert [entry.filename for entry in manifest.files] == [
        "light_metadata-000.zip",
        "projects-000.zip",
        "memories-000.zip",
        "frames-000.zip",
        "conversations-000.zip",
    ]
    assert all(entry.part == 0 for entry in manifest.files)


def test_the_root_keys_that_are_not_the_file_list_are_kept(tmp_path: Path) -> None:
    """`created_at` (cuándo generó Anthropic el export) no se descarta: CLAUDE.md §1.3.

    Es la única fecha que `convert` puede poner en el README de la salida sin mirar el
    reloj (CLAUDE.md §1.4). Las URLs de descarga se siguen tirando siempre.
    """
    path = _write(
        tmp_path,
        {
            "created_at": "2026-09-18T16:59:47.566776+00:00",
            "version": "1.0",
            "export_url": "https://example.com/expira",
            "data_files": [{"category": "memories", "part": 0}],
        },
    )

    manifest = parse_manifest(path)

    assert (manifest.model_extra or {})["created_at"] == "2026-09-18T16:59:47.566776+00:00"
    assert (manifest.model_extra or {})["version"] == "1.0"
    assert "export_url" not in (manifest.model_extra or {})


def test_urls_are_pruned_at_every_depth_not_only_at_the_root(tmp_path: Path) -> None:
    """CLAUDE.md §1.5: una URL de descarga no sobrevive esté donde esté.

    Antes la poda miraba solo el primer nivel del diccionario, así que un
    `delivery.url` anidado acababa intacto en `Manifest.extra` y de ahí a
    `_report/inventory.json`. Son de un solo uso y expiran: no se guardan nunca.
    """
    path = _write(
        tmp_path,
        {
            "created_at": "2026-09-18T16:59:47.566776+00:00",
            "delivery": {
                "url": "https://example.com/uno",
                "export_url": "https://example.com/dos",
                "region": "eu",
            },
            "links": [{"download_url": "https://example.com/tres"}, {"kind": "zip"}],
            "data_files": [
                {
                    "category": "memories",
                    "part": 0,
                    "delivery": {"signedUrl": "https://example.com/cuatro", "bytes": 12},
                }
            ],
        },
    )

    manifest = parse_manifest(path)
    extra = manifest.model_extra or {}

    assert "https://example.com" not in json.dumps(manifest.model_dump(mode="json"))
    assert extra["delivery"] == {"region": "eu"}
    assert extra["links"] == [{}, {"kind": "zip"}]
    assert (manifest.files[0].model_extra or {})["delivery"] == {"bytes": 12}
    # Podar no puede costar la información que sí sirve.
    assert extra["created_at"] == "2026-09-18T16:59:47.566776+00:00"
    assert manifest.declared_parts() == {"memories": [0]}


def test_declared_parts_from_top_level_array_and_filename(tmp_path: Path) -> None:
    path = _write(tmp_path, [{"filename": "conversations-002.zip"}, {"filename": "frames-000.zip"}])
    manifest = parse_manifest(path)
    assert manifest.declared_parts() == {"conversations": [2], "frames": [0]}


def test_unrecognised_manifest_yields_no_declarations(tmp_path: Path) -> None:
    path = _write(tmp_path, {"member_uuid": "aaaa", "something_else": 1})
    manifest = parse_manifest(path)
    assert manifest.declared_parts() == {}


def test_export_urls_are_never_used(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {"files": [{"category": "memories", "part": 0, "export_url": "https://example.com/x"}]},
    )
    manifest = parse_manifest(path)
    assert manifest.declared_parts() == {"memories": [0]}
    assert "export_url" not in manifest.model_dump(mode="json")["files"][0]


def test_broken_manifest_does_not_break_the_inventory(tmp_path: Path) -> None:
    root = tmp_path / "export"
    (root / "memories-000").mkdir(parents=True)
    (root / "memories-000" / "profile.md").write_text("# Perfil\n", encoding="utf-8")
    (root / "member-manifest-2026-02-01.json").write_text("{not json", encoding="utf-8")

    inventory = build_inventory(create_source(root))

    assert "memories" in inventory.categories
    assert any("manifiesto" in w.lower() for w in inventory.warnings)


def test_manifest_path_as_source_uses_its_folder(tmp_path: Path) -> None:
    root = tmp_path / "export"
    (root / "memories-000").mkdir(parents=True)
    (root / "memories-000" / "profile.md").write_text("# Perfil\n", encoding="utf-8")
    manifest_path = _write(root, {"files": [{"category": "memories", "part": 0}]})

    inventory = build_inventory(create_source(manifest_path))

    assert inventory.root == "export"
    assert inventory.missing_parts == {}


def test_unsupported_input_raises_unknown_format(tmp_path: Path) -> None:
    other = tmp_path / "notas.txt"
    other.write_text("hola", encoding="utf-8")
    with pytest.raises(UnknownFormatError):
        create_source(other)


def test_empty_folder_raises_unknown_format(tmp_path: Path) -> None:
    empty = tmp_path / "vacio"
    empty.mkdir()
    with pytest.raises(UnknownFormatError):
        build_inventory(create_source(empty))
