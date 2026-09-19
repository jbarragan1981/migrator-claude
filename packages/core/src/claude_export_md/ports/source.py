"""Puerto `ExportSource`: de dónde salen los bytes del export.

Implementaciones: `adapters/source_folder.py` (carpetas ya extraídas y/o zips sueltos)
y `adapters/source_zip.py` (un único .zip). El puerto es deliberadamente mínimo:
enumerar archivos con su categoría/parte, abrirlos como stream binario, y decir qué
declara el manifiesto. Todo lo demás (muestreo, validación) vive en los casos de uso.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import IO, Protocol, runtime_checkable

from claude_export_md.domain.manifest import Manifest

#: Naturaleza del archivo, decidida por el adapter a partir de la extensión.
JSON = "json"
MARKDOWN = "markdown"
OTHER = "other"


@dataclass(frozen=True, slots=True)
class SourceFile:
    """Un archivo dentro del export, identificado por su ruta de presentación.

    `path` es relativa a la raíz del export y en formato POSIX; para miembros de un
    zip se usa `"<zip>!/<miembro>"`. Es la clave con la que `open_file` lo resuelve.
    """

    category: str
    part: int
    path: str
    bytes: int
    kind: str = OTHER


@runtime_checkable
class ExportSource(Protocol):
    """Fuente de un export ya presente en disco (nunca se descarga nada)."""

    @property
    def root(self) -> str:
        """Nombre (no ruta absoluta) de la carpeta o zip de origen."""

    @property
    def format_version(self) -> str:
        """`"batched-manifest"` o `"legacy-single-zip"`, según el layout detectado."""

    def files(self) -> Sequence[SourceFile]:
        """Todos los archivos descubiertos, ordenados de forma determinista."""

    def manifest(self) -> Manifest | None:
        """Manifiesto ya parseado, o `None` si el export no trae uno.

        Lanza `CorruptFileError` si hay manifiesto pero no se puede leer; el caso de
        uso lo convierte en advertencia (un manifiesto roto no invalida el export).
        """

    def open_file(self, file: SourceFile) -> AbstractContextManager[IO[bytes]]:
        """Abre el archivo como stream binario. Se puede llamar varias veces."""


__all__ = ["JSON", "MARKDOWN", "OTHER", "ExportSource", "SourceFile"]
