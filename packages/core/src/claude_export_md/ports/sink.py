"""Puerto `MarkdownSink`: a dónde va el árbol Markdown que produce la conversión.

Implementación actual: `adapters/sink_filesystem.py` (`FilesystemSink`). Están
previstos un `ZipSink` (M3, para `GET /exports/{id}/download`) y una bóveda de
Obsidian (CLAUDE.md §4).

El puerto es deliberadamente mínimo —comprobar que se puede escribir y escribir un
archivo de texto— y a propósito NO sabe de `Memory`, `Conversation` ni de Jinja2: el
render ya ocurrió y lo que le llega es texto (ADR-0006). Las rutas son SIEMPRE
relativas a la raíz del sink y en formato POSIX (`conversations/2026/01/….md`), las
mismas que decide `rendering/`, para que el árbol salga igual en Windows, dentro de un
zip o en memoria.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MarkdownSink(Protocol):
    """Destino del árbol Markdown de una conversión."""

    @property
    def location(self) -> str:
        """Dónde escribe, para poder decírselo al usuario (una carpeta, un zip…)."""

    def ensure_writable(self, overwrite: bool = False) -> None:
        """Comprueba que se puede escribir ANTES de escribir el primer byte.

        Lanza `OutputNotEmptyError` si el destino ya tiene contenido y no se pidió
        `overwrite` (spec 05 CA-3). `overwrite` autoriza a sobrescribir lo que la
        conversión regenera; no es permiso para borrar lo que ya hubiera.
        """

    def write(self, path: str, content: str) -> None:
        """Escribe `content` en `path`, sobrescribiendo si ya existía (idempotencia).

        `path` es relativa a la raíz del sink y en formato POSIX.
        """


__all__ = ["MarkdownSink"]
