"""Utilidades compartidas por los tests de core.

Todos los fixtures son SINTÉTICOS (datos inventados). Nunca se usa `exports/`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


def write_manifest(root: Path, declared: dict[str, list[int]], **extra: Any) -> Path:
    """Escribe un `member-manifest-*.json` sintético dentro de `root`.

    Los manifiestos no se pueden commitear (`.gitignore` ignora `member-manifest-*.json`),
    así que los tests que los necesitan los generan en `tmp_path`.
    """
    files = [
        {
            "category": category,
            "part": part,
            "filename": f"{category}-{part:03d}.zip",
            "export_url": "https://example.com/export/placeholder",
        }
        for category, parts in sorted(declared.items())
        for part in sorted(parts)
    ]
    payload: dict[str, Any] = {"files": files, **extra}
    path = root / "member-manifest-2026-02-01.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def make_big_array(path: Path, items: int) -> Path:
    """Genera un JSON array grande (sin pretty-print) para los tests de muestreo."""
    with path.open("w", encoding="utf-8") as fp:
        fp.write("[")
        for i in range(items):
            if i:
                fp.write(",")
            fp.write(
                json.dumps(
                    {
                        "uuid": f"{i:08d}-0000-4000-8000-000000000000",
                        "name": f"Conversacion sintetica {i}",
                        "created_at": "2026-01-01T00:00:00.000000Z",
                        "chat_messages": [{"uuid": f"m{i}", "sender": "human", "text": "x" * 120}],
                    }
                )
            )
        fp.write("]")
    return path
