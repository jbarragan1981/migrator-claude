"""Volcado a JSON estable del `Inventory` y del `Report` (spec 01 CA-6, spec 04 CA-8).

Claves ordenadas, UTF-8 sin escapes, indentación fija y salto final: dos corridas
sobre el mismo export producen exactamente los mismos bytes.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from claude_export_md.domain.entities import ParseError
from claude_export_md.domain.inventory import Inventory

logger = logging.getLogger(__name__)


def _dumps(payload: Any) -> str:  # noqa: ANN401 - cualquier estructura serializable
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def dumps_inventory(inventory: Inventory) -> str:
    """Serializa el inventario de forma determinista."""
    return _dumps(inventory.model_dump(mode="json"))


def dumps_summary(summary: Mapping[str, Any]) -> str:
    """Serializa `_report/summary.json` de forma determinista (spec 04 CA-8)."""
    return _dumps(dict(summary))


def dumps_errors(errors: Iterable[ParseError]) -> str:
    """`_report/errors.jsonl`: una línea JSON por `ParseError`, en orden de aparición.

    Sin errores devuelve la cadena vacía (el archivo se escribe igual, vacío: así el
    árbol de salida no cambia de forma según haya habido problemas o no).
    """
    return "".join(
        json.dumps(error.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
        for error in errors
    )


def write_inventory(inventory: Inventory, out: Path | str) -> None:
    """Escribe el inventario en `out`, creando la carpeta padre si hace falta."""
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_inventory(inventory), encoding="utf-8")
    logger.info("Inventario escrito en %s", path)
