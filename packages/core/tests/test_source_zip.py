"""CA-4: los zips se inventarían en streaming, sin extraerlos a disco."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from claude_export_md import build_inventory, create_source

CONVERSATIONS = [
    {
        "uuid": "11111111-1111-4111-8111-111111111111",
        "name": "Conversacion en zip",
        "created_at": "2026-01-02T10:00:00.000000Z",
        "chat_messages": [{"uuid": "m1", "sender": "human", "text": "hola"}],
    }
]


def _make_zip(path: Path, members: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return path


def test_folder_of_zips_is_inventoried_without_extracting(tmp_path: Path) -> None:
    root = tmp_path / "export"
    _make_zip(
        root / "conversations-000.zip",
        {"conversations.json": json.dumps(CONVERSATIONS)},
    )
    _make_zip(
        root / "memories-000.zip",
        {"profile.md": "# Perfil\n", "people/ana.md": "# Ana\n"},
    )
    before = sorted(p.name for p in root.iterdir())

    inventory = build_inventory(create_source(root))

    assert inventory.format_version == "batched-manifest"
    assert sorted(inventory.categories) == ["conversations", "memories"]
    conversations = inventory.categories["conversations"]
    assert conversations.root_type == "array"
    assert conversations.files[0].path == "conversations-000.zip!/conversations.json"
    assert conversations.files[0].item_shapes[0]["uuid"] == "string"  # type: ignore[index]
    assert inventory.categories["memories"].approx_item_count == 2
    # Nada se extrajo a disco.
    assert sorted(p.name for p in root.iterdir()) == before


def test_single_category_zip_as_source(tmp_path: Path) -> None:
    zip_path = _make_zip(
        tmp_path / "conversations-000.zip",
        {"conversations.json": json.dumps(CONVERSATIONS)},
    )
    inventory = build_inventory(create_source(zip_path))

    assert inventory.root == "conversations-000.zip"
    assert inventory.categories["conversations"].parts == [0]


def test_legacy_single_zip_is_detected(tmp_path: Path) -> None:
    zip_path = _make_zip(
        tmp_path / "data-2025-03-01.zip",
        {
            "conversations.json": json.dumps(CONVERSATIONS),
            "projects.json": "[]",
            "users.json": "[]",
        },
    )
    inventory = build_inventory(create_source(zip_path))

    assert inventory.format_version == "legacy-single-zip"
    assert sorted(inventory.categories) == ["conversations", "projects", "users"]


def test_dated_zip_name_does_not_collapse_the_categories(tmp_path: Path) -> None:
    """`claude-export-2026-02-01.zip` no es `claude-export-2026-02` parte 1."""
    zip_path = _make_zip(
        tmp_path / "claude-export-2026-02-01.zip",
        {
            "conversations-000/conversations.json": json.dumps(CONVERSATIONS),
            "memories-000/people/ana-real.md": "# Ana\n",
            "projects-000/projects.json": "[]",
        },
    )

    inventory = build_inventory(create_source(zip_path))

    assert sorted(inventory.categories) == ["conversations", "memories", "projects"]
    assert inventory.categories["memories"].files[0].pattern == "memories-000/people/*.md"


def test_corrupt_zip_is_skipped_with_a_warning(tmp_path: Path) -> None:
    root = tmp_path / "export"
    root.mkdir()
    (root / "frames-000.zip").write_bytes(b"esto no es un zip")
    _make_zip(root / "conversations-000.zip", {"conversations.json": json.dumps(CONVERSATIONS)})

    inventory = build_inventory(create_source(root))

    assert sorted(inventory.categories) == ["conversations"]
    assert "frames" in inventory.missing_categories


def test_parts_greater_than_zero_are_grouped(tmp_path: Path) -> None:
    root = tmp_path / "export"
    _make_zip(root / "conversations-000.zip", {"conversations.json": json.dumps(CONVERSATIONS)})
    _make_zip(root / "conversations-001.zip", {"conversations.json": json.dumps(CONVERSATIONS)})

    inventory = build_inventory(create_source(root))

    assert inventory.categories["conversations"].parts == [0, 1]
    assert len(inventory.categories["conversations"].files) == 2
