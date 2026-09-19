"""Modelo del `member-manifest-*.json`.

Solo se usa para VALIDAR qué categorías y partes declara el export frente a lo que
hay en disco (CLAUDE.md §9). Las URLs de descarga (`export_url`) son de un solo uso
y se descartan al entrar: nunca se guardan ni se usan.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

#: Sufijo de parte tal como lo emite Anthropic: SIEMPRE con ceros a la izquierda
#: (`conversations-000`, `-012`, `-123`) y de 3 a 6 dígitos. Exigir el cero inicial a
#: partir de 4 dígitos es lo que distingue una parte de un año: `claude-export-2026` y
#: `data-2025-03-01` NO son partes (antes `data-2025-03-01` daba `("data-2025-03", 1)`
#: y colapsaba las 5 categorías de un zip fechado en una categoría inventada).
_PART_SUFFIX = re.compile(r"^(?P<category>.+?)[-_](?P<part>\d{3}|0\d{3,5})(?:\.zip)?$")


def split_part_suffix(name: str) -> tuple[str, int] | None:
    """`conversations-000.zip` → `("conversations", 0)`. `None` si no tiene sufijo de parte."""
    match = _PART_SUFFIX.match(name)
    if match is None:
        return None
    return match.group("category"), int(match.group("part"))


class ManifestFile(BaseModel):
    """Un archivo declarado por el manifiesto. Campos desconocidos se conservan."""

    model_config = ConfigDict(extra="allow", frozen=True)

    category: str | None = None
    part: int | None = None
    filename: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data: Any) -> Any:
        """Reduce una entrada del manifiesto a `category` / `part` / `filename`.

        Fase 0 confirmó contra un export real (`docs/export-format/manifest.md`) que las
        entradas de `data_files[]` usan exactamente `category`, `part` y `filename` (más
        `batch_index` y `export_url`, que se conservan en `extra` y se descartan
        respectivamente). Los alias restantes (`type`/`name`, `part_number`,
        `file`/`path`) siguen siendo conjetura sin confirmar: se mantienen por tolerancia.
        """
        if not isinstance(data, dict):
            return data
        # Nunca conservamos URLs de descarga (un solo uso, expiran, son secretos).
        values: dict[str, Any] = {k: v for k, v in data.items() if "url" not in k.lower()}
        category = values.get("category") or values.get("type") or values.get("name")
        part = values.get("part")
        if part is None:
            part = values.get("part_number")
        filename = values.get("filename") or values.get("file") or values.get("path")
        if isinstance(filename, str):
            guess = split_part_suffix(filename.rsplit("/", 1)[-1])
            if guess is not None:
                category = category or guess[0]
                part = guess[1] if part is None else part
        if isinstance(category, str):
            guess = split_part_suffix(category)
            if guess is not None:
                category, part = guess[0], guess[1] if part is None else part
        values["category"] = category if isinstance(category, str) else None
        values["part"] = part if isinstance(part, int) and not isinstance(part, bool) else None
        values["filename"] = filename if isinstance(filename, str) else None
        return values


class Manifest(BaseModel):
    """Manifiesto ya normalizado: qué categorías y partes dice que existen."""

    model_config = ConfigDict(extra="allow", frozen=True)

    path: str
    files: list[ManifestFile] = []

    def declared_parts(self) -> dict[str, list[int]]:
        declared: dict[str, set[int]] = {}
        for entry in self.files:
            if entry.category is None:
                continue
            declared.setdefault(entry.category, set()).add(entry.part or 0)
        return {category: sorted(parts) for category, parts in sorted(declared.items())}
