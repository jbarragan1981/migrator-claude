"""Utilidades compartidas por los tests de core.

Todos los fixtures son SINTÉTICOS (datos inventados). Nunca se usa `exports/`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

import pytest

from claude_export_md.domain.manifest import Manifest
from claude_export_md.ports.source import ExportSource, SourceFile

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


class CountingStream:
    """Stream que cuenta cuántos bytes se le han leído."""

    def __init__(self, inner: IO[bytes], counter: list[int]) -> None:
        self._inner = inner
        self._counter = counter

    def read(self, size: int = -1) -> bytes:
        data = self._inner.read(size)
        self._counter[0] += len(data)
        return data

    def close(self) -> None:
        self._inner.close()


class CountingSource:
    """Decorador de `ExportSource` que cuenta los bytes leídos del origen.

    Es la forma de comprobar que un parser no carga el archivo entero (CA-C3): si tras
    pedir el primer ítem solo se leyó una fracción del archivo, no hubo `json.load`.
    """

    def __init__(self, inner: ExportSource) -> None:
        self._inner = inner
        self.read_bytes = [0]

    @property
    def root(self) -> str:
        return self._inner.root

    @property
    def format_version(self) -> str:
        return self._inner.format_version

    def files(self) -> Sequence[SourceFile]:
        return self._inner.files()

    def manifest(self) -> Manifest | None:
        return self._inner.manifest()

    @contextmanager
    def open_file(self, file: SourceFile) -> Iterator[IO[bytes]]:
        with self._inner.open_file(file) as fp:
            yield CountingStream(fp, self.read_bytes)  # type: ignore[misc]
