"""Excepciones propias de claude_export_md (ver CLAUDE.md §4).

Regla: una excepción solo se lanza cuando el *input completo* no se puede procesar.
Los problemas de un ítem o de un archivo suelto se acumulan como advertencias/errores
en el resultado (`Inventory.warnings`, `Report.errors`), nunca detienen la corrida.
"""

from __future__ import annotations


class ClaudeExportMdError(Exception):
    """Base de todos los errores de la librería."""


class UnknownFormatError(ClaudeExportMdError):
    """El input no parece una exportación de Claude.ai (ni carpetas, ni zips, ni legacy)."""


class OutputNotEmptyError(ClaudeExportMdError):
    """La carpeta de salida ya tiene contenido y no se pidió `--overwrite` (spec 05 CA-3).

    Se comprueba ANTES de escribir nada: convertir sobre una carpeta que el usuario ya
    usaba para otra cosa mezclaría dos árboles sin avisar.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


class CorruptFileError(ClaudeExportMdError):
    """Un archivo del export no se puede leer o su JSON está roto."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason
