"""Lectura tolerante del `member-manifest-*.json`.

Anthropic no documenta el formato, pero la Fase 0 confirmó la forma real contra un
export de verdad (`docs/export-format/manifest.md`): la lista de archivos declarados
va bajo `data_files`. Se siguen aceptando otras claves por tolerancia, y de cada
entrada se deducen categoría y parte. Lo que no se reconoce no rompe nada: se
devuelve un manifiesto sin declaraciones y el inventario sigue adelante.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from claude_export_md.domain.manifest import Manifest, ManifestFile
from claude_export_md.domain.redaction import redact_text
from claude_export_md.errors import CorruptFileError

logger = logging.getLogger(__name__)

MANIFEST_GLOB = "member-manifest-*.json"
#: El manifiesto es un índice pequeño; si excede esto, sospechamos y no lo cargamos.
MAX_MANIFEST_BYTES = 5_000_000
#: Claves raíz donde puede estar la lista de archivos declarados, en orden de preferencia.
#: `data_files` es la ÚNICA confirmada contra un export real (Fase 0, ver
#: `docs/export-format/manifest.md`); va primero para que gane si conviven varias.
#: El resto sigue siendo conjetura sin confirmar (se mantienen por tolerancia a que el
#: formato cambie o a exports antiguos); no borrar sin evidencia de otro export.
_LIST_KEYS = ("data_files", "files", "exports", "parts", "data", "items", "artifacts")


def find_manifest(root: Path) -> Path | None:
    """Devuelve el manifiesto de la carpeta (el primero por orden alfabético) o `None`."""
    if not root.is_dir():
        return None
    candidates = sorted(root.glob(MANIFEST_GLOB))
    return candidates[0] if candidates else None


def _entries(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in _LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def parse_manifest(path: Path) -> Manifest:
    """Parsea el manifiesto. Lanza `CorruptFileError` si el JSON está roto."""
    size = path.stat().st_size
    if size > MAX_MANIFEST_BYTES:
        raise CorruptFileError(path.name, f"manifiesto inesperadamente grande ({size} bytes)")
    try:
        # El manifiesto es un índice de pocos KB: no necesita streaming (ver MAX_MANIFEST_BYTES).
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise CorruptFileError(path.name, str(exc)) from exc

    raw_entries = _entries(payload)
    if not raw_entries:
        # El nombre del manifiesto lleva el uuid de la cuenta: no se loguea en crudo.
        logger.warning("El manifiesto %s no declara archivos reconocibles", redact_text(path.name))
    files = [ManifestFile.model_validate(entry) for entry in raw_entries if isinstance(entry, dict)]
    return Manifest(path=path.name, files=files)
