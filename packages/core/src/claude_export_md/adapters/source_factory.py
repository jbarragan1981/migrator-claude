"""Elige el `ExportSource` adecuado según lo que el usuario apunte.

Entradas aceptadas (CLAUDE.md §9): una carpeta (con subcarpetas extraídas y/o zips),
un `.zip` suelto, o el propio `member-manifest-*.json` (se usa su carpeta).
"""

from __future__ import annotations

import logging
from pathlib import Path

from claude_export_md.adapters.source_folder import FolderSource
from claude_export_md.adapters.source_zip import ZipSource
from claude_export_md.errors import UnknownFormatError
from claude_export_md.ports.source import ExportSource

logger = logging.getLogger(__name__)


def create_source(path: Path | str) -> ExportSource:
    """Devuelve un `ExportSource` para `path` o lanza `UnknownFormatError`."""
    target = Path(path)
    if not target.exists():
        raise UnknownFormatError(f"{target} no existe")
    if target.is_dir():
        return FolderSource(target)
    suffix = target.suffix.lower()
    if suffix == ".zip":
        return ZipSource(target)
    if suffix == ".json" and target.name.startswith("member-manifest-"):
        logger.debug("Se apuntó al manifiesto; se inventaria su carpeta %s", target.parent.name)
        return FolderSource(target.parent)
    raise UnknownFormatError(
        f"No se reconoce {target.name} como exportación de Claude.ai: "
        "apunta a la carpeta del export, a un .zip o al member-manifest-*.json"
    )
