"""Resultado del caso de uso `inventory` (spec 01).

`Inventory` describe QUÉ hay en un export y con qué forma, nunca su contenido:
solo nombres de archivo, tamaños, tipo raíz y *shapes* (clave → tipo) de hasta
`SAMPLE_ITEMS` ítems. Es serializable a JSON estable (ver `adapters/sink_json.py`).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

#: Categorías que esperamos en una exportación de 2026. Solo sirven para AVISAR de
#: ausencias (`missing_categories`); el descubrimiento nunca se limita a esta lista.
EXPECTED_CATEGORIES: tuple[str, ...] = (
    "conversations",
    "frames",
    "light_metadata",
    "memories",
    "projects",
)

#: Categorías del export legacy (un solo zip con `conversations/projects/users.json`).
LEGACY_CATEGORIES: frozenset[str] = frozenset({"conversations", "projects", "users"})

#: Máximo de ítems que se materializan por archivo JSON (CA-3 del spec 01).
SAMPLE_ITEMS = 3

FormatVersion = Literal["batched-manifest", "legacy-single-zip"]

BATCHED_MANIFEST: FormatVersion = "batched-manifest"
LEGACY_SINGLE_ZIP: FormatVersion = "legacy-single-zip"

#: Tipo raíz observado: "array" | "object" | "markdown" | "mixed" | "other" | "unknown".
RootType = str


class FileInventory(BaseModel):
    """Una entrada del inventario: tamaño, tipo raíz y muestra de la estructura.

    Es **un archivo nombrable** (`path`) o **un grupo de archivos** (`pattern` + `count`),
    nunca las dos cosas. Solo se conserva el nombre literal cuando lo decide el formato
    del export y no el contenido del usuario (`domain/redaction.py`, ADR-0004): los
    nombres hoja variables —`memories-000/people/<persona>.md`— se colapsan en
    `{"pattern": "memories-000/people/*.md", "count": 37}`.
    """

    model_config = ConfigDict(extra="allow", frozen=True)

    #: Ruta de presentación literal, solo para nombres predecibles (`conversations-001.json`).
    path: str | None = None
    #: Glob del grupo cuando el nombre hoja es variable. Excluyente con `path`.
    pattern: str | None = None
    #: Archivos representados por esta entrada (1 cuando es un archivo nombrado).
    count: int = 1
    bytes: int
    part: int
    root_type: RootType = "unknown"
    #: Claves de primer nivel cuando la raíz es un objeto JSON.
    top_keys: list[str] = []
    #: `shape` (clave → tipo) de los primeros ítems cuando la raíz es un array JSON.
    item_shapes: list[dict[str, Any] | str] = []
    approx_item_count: int | None = None
    item_count_exact: bool = False
    #: `True` si se cortó el muestreo por límite de eventos (archivos enormes).
    truncated: bool = False
    error: str | None = None

    @property
    def label(self) -> str:
        """Cómo se nombra esta entrada en tablas y advertencias (ya redactada)."""
        return self.path or self.pattern or "?"


class CategoryInventory(BaseModel):
    """Agregado por categoría (`conversations`, `memories`, …) y sus partes."""

    model_config = ConfigDict(extra="allow", frozen=True)

    name: str
    parts: list[int] = []
    #: Entradas: archivos nombrables y grupos. `len(files)` NO es el nº de archivos.
    files: list[FileInventory] = []
    #: Archivos reales de la categoría (suma de `FileInventory.count`).
    file_count: int = 0
    total_bytes: int = 0
    root_type: RootType = "unknown"
    approx_item_count: int | None = None
    item_count_exact: bool = False


class Inventory(BaseModel):
    """Foto completa del export. Sin rutas absolutas ni fecha de la corrida (CA-6)."""

    model_config = ConfigDict(extra="allow", frozen=True)

    #: Nombre (no ruta absoluta) de la carpeta o zip de origen: no filtra el disco del usuario.
    root: str
    format_version: FormatVersion
    categories: dict[str, CategoryInventory] = {}
    missing_categories: list[str] = []
    missing_parts: dict[str, list[int]] = {}
    manifest_path: str | None = None
    warnings: list[str] = []
