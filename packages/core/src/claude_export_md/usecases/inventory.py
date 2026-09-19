"""Caso de uso `inventory` (spec 01): qué hay en el export y con qué forma.

Nunca carga un archivo completo: de cada JSON array se materializan como mucho
`SAMPLE_ITEMS` ítems con `ijson` (CA-3) y de cada JSON objeto solo sus claves de
primer nivel. El número de ítems de un array grande es una ESTIMACIÓN a partir del
tamaño medio de los ítems muestreados; nunca se recorre el archivo entero.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from typing import IO, Any

import ijson

from claude_export_md.domain.inventory import (
    BATCHED_MANIFEST,
    EXPECTED_CATEGORIES,
    LEGACY_CATEGORIES,
    LEGACY_SINGLE_ZIP,
    SAMPLE_ITEMS,
    CategoryInventory,
    FileInventory,
    Inventory,
)
from claude_export_md.domain.redaction import describe_path, label_of, redact_text
from claude_export_md.errors import CorruptFileError, UnknownFormatError
from claude_export_md.ports.source import JSON, MARKDOWN, ExportSource, SourceFile

logger = logging.getLogger(__name__)

#: Bytes que se leen para decidir si la raíz del JSON es array u objeto.
PEEK_BYTES = 64
#: Claves de primer nivel que como mucho se listan de un JSON objeto.
MAX_TOP_KEYS = 200
#: Techo de eventos de ijson al recorrer un objeto (evita pasearse 800 MB por gusto).
MAX_EVENTS = 200_000
#: Profundidad máxima del `shape` de un ítem. 5 niveles bastan para ver
#: `conversation.chat_messages[0].content[0]`, que es lo que pide CLAUDE.md §4.
MAX_SHAPE_DEPTH = 5
#: Claves máximas por nivel del `shape`.
MAX_SHAPE_KEYS = 40

_WHITESPACE = b" \t\r\n"
_BOM = b"\xef\xbb\xbf"


def shape(value: Any, depth: int = 0) -> Any:
    """Estructura de un valor JSON: claves → tipo, sin ningún dato real.

    Una clave con forma de UUID o de correo ES un dato real (un objeto indexado por
    id o por persona), así que se enmascara como `<uuid>` / `<email>` (ADR-0004).
    """
    if isinstance(value, dict):
        if depth >= MAX_SHAPE_DEPTH:
            return "object"
        items = list(value.items())[:MAX_SHAPE_KEYS]
        return {redact_text(str(key)): shape(item, depth + 1) for key, item in items}
    if isinstance(value, list):
        if depth >= MAX_SHAPE_DEPTH:
            return "array"
        return [shape(value[0], depth + 1)] if value else []
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def _peek_root_type(stream: IO[bytes]) -> str:
    head = stream.read(PEEK_BYTES).lstrip(_BOM).lstrip(_WHITESPACE)
    if head.startswith(b"["):
        return "array"
    if head.startswith(b"{"):
        return "object"
    return "unknown"


def _sample_array(stream: IO[bytes], size: int) -> tuple[list[Any], int | None, bool]:
    shapes: list[Any] = []
    lengths: list[int] = []
    for item in ijson.items(stream, "item", use_float=True):
        shapes.append(shape(item))
        lengths.append(len(json.dumps(item, ensure_ascii=False, default=str)))
        if len(shapes) >= SAMPLE_ITEMS:
            break
    if len(shapes) < SAMPLE_ITEMS:
        return shapes, len(shapes), True  # el array cabía en la muestra: conteo exacto
    average = sum(lengths) / len(lengths)
    approx = max(SAMPLE_ITEMS, round((size - 2) / (average + 1)))
    return shapes, approx, False


def _sample_object(stream: IO[bytes]) -> tuple[list[str], bool]:
    keys: list[str] = []
    truncated = False
    for index, (prefix, event, value) in enumerate(ijson.parse(stream, use_float=True)):
        if prefix == "" and event == "map_key" and isinstance(value, str):
            # Una clave con forma de UUID/correo es un dato del usuario, no una clave.
            keys.append(redact_text(value))
        if len(keys) >= MAX_TOP_KEYS or index >= MAX_EVENTS:
            truncated = True
            break
    return keys, truncated


def _identity(file: SourceFile) -> dict[str, Any]:
    """Cómo se nombra este archivo en el inventario: literal o patrón (ADR-0004)."""
    path, pattern = describe_path(file.path, file.category)
    return {"path": path, "pattern": pattern, "bytes": file.bytes, "part": file.part}


def _inventory_json(source: ExportSource, file: SourceFile) -> FileInventory:
    identity = _identity(file)
    with source.open_file(file) as stream:
        root_type = _peek_root_type(stream)
    if root_type == "unknown":
        return FileInventory(
            **identity,
            root_type=root_type,
            error="la raíz del JSON no es ni array ni objeto",
        )
    with source.open_file(file) as stream:
        if root_type == "array":
            shapes, approx, exact = _sample_array(stream, file.bytes)
            return FileInventory(
                **identity,
                root_type=root_type,
                item_shapes=shapes,
                approx_item_count=approx,
                item_count_exact=exact,
            )
        keys, truncated = _sample_object(stream)
        return FileInventory(
            **identity,
            root_type=root_type,
            top_keys=keys,
            truncated=truncated,
        )


def _inventory_file(source: ExportSource, file: SourceFile, warnings: list[str]) -> FileInventory:
    if file.kind == MARKDOWN:
        return FileInventory(
            **_identity(file),
            root_type="markdown",
            approx_item_count=1,
            item_count_exact=True,
        )
    if file.kind != JSON:
        return FileInventory(**_identity(file), root_type="other")
    try:
        return _inventory_json(source, file)
    except (CorruptFileError, ijson.JSONError, ValueError, OSError, UnicodeDecodeError) as exc:
        # Ni el log ni la advertencia (que viaja dentro del JSON) nombran el archivo.
        reason = redact_text(str(exc))
        label = label_of(file.path, file.category)
        logger.warning("No se pudo inspeccionar %s: %s", label, reason)
        warnings.append(f"{label}: no se pudo inspeccionar ({reason})")
        return FileInventory(**_identity(file), root_type="unknown", error=reason)


def _merge_root_type(entries: Sequence[FileInventory]) -> str:
    root_types = {e.root_type for e in entries if e.root_type not in {"other", "unknown"}}
    if len(root_types) == 1:
        return root_types.pop()
    if root_types:
        return "mixed"
    return "unknown"


def _first[T](values: Iterable[T], default: T) -> T:
    return next(iter(values), default)


def _merge_group(entries: list[FileInventory]) -> FileInventory:
    """Colapsa los archivos de un mismo patrón y parte en una sola entrada."""
    if len(entries) == 1:
        return entries[0]
    counted = [e.approx_item_count for e in entries if e.approx_item_count is not None]
    return FileInventory(
        pattern=entries[0].pattern,
        count=sum(e.count for e in entries),
        bytes=sum(e.bytes for e in entries),
        part=entries[0].part,
        root_type=_merge_root_type(entries),
        top_keys=_first((e.top_keys for e in entries if e.top_keys), []),
        item_shapes=_first((e.item_shapes for e in entries if e.item_shapes), [])[:SAMPLE_ITEMS],
        approx_item_count=sum(counted) if counted else None,
        item_count_exact=all(e.item_count_exact for e in entries),
        truncated=any(e.truncated for e in entries),
        error=_first((e.error for e in entries if e.error), None),
    )


def _group(entries: list[FileInventory]) -> list[FileInventory]:
    """Un archivo nombrable por entrada; los de nombre variable, uno por patrón."""
    named = [e for e in entries if e.pattern is None]
    grouped: dict[tuple[str, int], list[FileInventory]] = {}
    for entry in entries:
        if entry.pattern is not None:
            grouped.setdefault((entry.pattern, entry.part), []).append(entry)
    merged = [_merge_group(group) for _, group in sorted(grouped.items())]
    return sorted(named + merged, key=lambda e: (e.part, e.label))


def _aggregate(name: str, entries: list[FileInventory]) -> CategoryInventory:
    files = _group(entries)
    counted = [f.approx_item_count for f in files if f.approx_item_count is not None]
    return CategoryInventory(
        name=name,
        parts=sorted({f.part for f in files}),
        files=files,
        file_count=sum(f.count for f in files),
        total_bytes=sum(f.bytes for f in files),
        root_type=_merge_root_type(files),
        approx_item_count=sum(counted) if counted else None,
        item_count_exact=bool(files) and all(f.item_count_exact for f in files),
    )


def _redact_categories(declared: dict[str, list[int]]) -> dict[str, list[int]]:
    """Redacta los nombres de categoría declarados por el manifiesto.

    Hoy son valores fijos (`conversations`, `memories`…), pero salen de un archivo del
    usuario y terminan en `warnings`, `missing_categories` y en las claves de
    `missing_parts`: se tratan como texto libre (ADR-0004). Si dos nombres colapsan al
    redactarse, sus partes se unen.
    """
    merged: dict[str, set[int]] = {}
    for category, parts in declared.items():
        merged.setdefault(redact_text(category), set()).update(parts)
    return {category: sorted(parts) for category, parts in sorted(merged.items())}


def _read_manifest_parts(
    source: ExportSource, warnings: list[str]
) -> tuple[dict[str, list[int]], str | None]:
    try:
        manifest = source.manifest()
    except CorruptFileError as exc:
        # El mensaje trae el NOMBRE del manifiesto, que lleva el uuid de la cuenta.
        reason = redact_text(str(exc))
        logger.warning("Manifiesto ilegible: %s", reason)
        warnings.append(
            f"No se pudo leer el manifiesto ({reason}); se omite la validación de partes"
        )
        return {}, None
    if manifest is None:
        return {}, None
    declared = _redact_categories(manifest.declared_parts())
    # El nombre del manifiesto puede traer el uuid o el correo del miembro.
    path = redact_text(manifest.path)
    if not declared:
        warnings.append(f"El manifiesto {path} no declara categorías reconocibles")
    return declared, path


def build_inventory(source: ExportSource) -> Inventory:
    """Recorre el export y describe cada categoría sin cargar ningún archivo entero."""
    warnings: list[str] = []
    grouped: dict[str, list[FileInventory]] = {}
    for file in source.files():
        grouped.setdefault(file.category, []).append(_inventory_file(source, file, warnings))

    if not grouped:
        raise UnknownFormatError(
            f"No se reconoció ninguna categoría en {source.root}: "
            "¿es la carpeta del export de Claude.ai?"
        )

    categories = {name: _aggregate(name, grouped[name]) for name in sorted(grouped)}
    declared, manifest_path = _read_manifest_parts(source, warnings)

    format_version = (
        LEGACY_SINGLE_ZIP if source.format_version == LEGACY_SINGLE_ZIP else BATCHED_MANIFEST
    )
    baseline = (
        LEGACY_CATEGORIES if format_version == LEGACY_SINGLE_ZIP else set(EXPECTED_CATEGORIES)
    )
    expected = set(baseline) | set(declared)
    missing_categories = sorted(expected - set(categories))
    if missing_categories:
        warnings.append(f"Categorías ausentes: {', '.join(missing_categories)}")

    missing_parts: dict[str, list[int]] = {}
    for category, parts in declared.items():
        present = categories.get(category)
        if present is None:
            continue
        absent = sorted(set(parts) - set(present.parts))
        if absent:
            missing_parts[category] = absent
            warnings.append(
                f"Partes declaradas y ausentes en {category}: "
                f"{', '.join(str(part) for part in absent)}"
            )

    return Inventory(
        root=source.root,
        format_version=format_version,
        categories=categories,
        missing_categories=missing_categories,
        missing_parts=missing_parts,
        manifest_path=manifest_path,
        warnings=warnings,
    )
