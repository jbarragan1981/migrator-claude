"""El volcado a JSON del inventario: ordenado, UTF-8 y determinista (CA-6)."""

from __future__ import annotations

import json
from pathlib import Path

from claude_export_md import build_inventory, create_source, dumps_inventory, write_inventory


def test_write_inventory_creates_parent_dirs_and_sorted_json(
    tmp_path: Path, fixtures_dir: Path
) -> None:
    inventory = build_inventory(create_source(fixtures_dir / "batched-full"))
    out = tmp_path / "docs" / "export-format" / "inventory.json"

    write_inventory(inventory, out)

    text = out.read_text(encoding="utf-8")
    assert text == dumps_inventory(inventory)
    assert text.endswith("\n")
    payload = json.loads(text)
    assert list(payload) == sorted(payload)
    assert payload["format_version"] == "batched-manifest"


def test_write_inventory_is_idempotent(tmp_path: Path, fixtures_dir: Path) -> None:
    out = tmp_path / "inventory.json"
    source = create_source(fixtures_dir / "batched-full")
    write_inventory(build_inventory(source), out)
    first = out.read_bytes()
    write_inventory(build_inventory(create_source(fixtures_dir / "batched-full")), out)
    assert out.read_bytes() == first
