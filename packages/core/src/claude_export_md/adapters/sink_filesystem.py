"""`FilesystemSink`: el árbol Markdown escrito en una carpeta del disco.

Adapter del puerto `ports/sink.py` (ADR-0006) y único punto de I/O de la salida. No
sabe qué está escribiendo: recibe una ruta relativa POSIX y un texto ya renderizado
(`rendering/`), y quién le pide qué y en qué orden lo decide `usecases/convert.py`.

Determinismo (CLAUDE.md §1.4): siempre UTF-8 y siempre saltos `\\n`, también en
Windows, para que dos corridas —en la misma máquina o en otra— produzcan bytes
idénticos.
"""

from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath

from claude_export_md.errors import OutputNotEmptyError

logger = logging.getLogger(__name__)

#: Codificación y fin de línea de todo lo que se escribe.
ENCODING = "utf-8"
NEWLINE = "\n"


def ensure_writable(out: Path | str, overwrite: bool = False) -> Path:
    """Comprueba que se puede escribir en `out` ANTES de tocar nada (spec 05 CA-3).

    La carpeta puede no existir (se crea al escribir) o existir vacía. Si tiene
    contenido hace falta `overwrite`, que NO borra nada: solo autoriza a sobrescribir
    los archivos que la conversión regenera. Un archivo suelto donde debería ir la
    carpeta se rechaza siempre.
    """
    path = Path(out)
    if path.exists() and not path.is_dir():
        raise OutputNotEmptyError(str(path), "existe y no es una carpeta")
    if path.is_dir() and any(path.iterdir()) and not overwrite:
        raise OutputNotEmptyError(
            str(path), "la carpeta de salida no está vacía; usá --overwrite para escribir igual"
        )
    return path


def write_text(path: Path, content: str) -> Path:
    """Escribe un archivo de texto creando su carpeta; sobrescribe si ya existía."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=ENCODING, newline=NEWLINE)
    return path


class FilesystemSink:
    """`MarkdownSink` sobre una carpeta: `write("a/b.md", …)` → `<root>/a/b.md`."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @property
    def location(self) -> str:
        """La carpeta de salida, tal como la escribió quien llamó."""
        return str(self.root)

    def ensure_writable(self, overwrite: bool = False) -> None:
        """Ver `ports.sink.MarkdownSink.ensure_writable`."""
        ensure_writable(self.root, overwrite)

    def resolve(self, path: str) -> Path:
        """Ruta en disco de una ruta relativa POSIX del árbol de salida."""
        return self.root.joinpath(*PurePosixPath(path).parts)

    def write(self, path: str, content: str) -> None:
        """Ver `ports.sink.MarkdownSink.write`."""
        write_text(self.resolve(path), content)


__all__ = [
    "ENCODING",
    "NEWLINE",
    "FilesystemSink",
    "ensure_writable",
    "write_text",
]
