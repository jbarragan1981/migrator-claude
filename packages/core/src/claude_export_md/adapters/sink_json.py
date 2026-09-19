"""Volcado del `Inventory` a JSON estable (CA-6 del spec 01).

Claves ordenadas, UTF-8 sin escapes, indentación fija y salto final: dos corridas
sobre el mismo export producen exactamente los mismos bytes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from claude_export_md.domain.inventory import Inventory

logger = logging.getLogger(__name__)


def dumps_inventory(inventory: Inventory) -> str:
    """Serializa el inventario de forma determinista."""
    return (
        json.dumps(
            inventory.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def write_inventory(inventory: Inventory, out: Path | str) -> None:
    """Escribe el inventario en `out`, creando la carpeta padre si hace falta."""
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_inventory(inventory), encoding="utf-8")
    logger.info("Inventario escrito en %s", path)
