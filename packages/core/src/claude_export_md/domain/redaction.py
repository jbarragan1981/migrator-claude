"""Redacción del inventario: qué nombres pueden salir del disco del usuario (ADR-0004).

El inventario describe la FORMA del export y se comparte (`docs/export-format/`).
Un nombre de archivo hoja de una carpeta de Markdown (`memories-000/people/<persona>.md`)
está derivado del contenido: es contenido, y nunca se serializa. Solo se conserva el
nombre literal cuando es predecible, es decir cuando lo eligió Anthropic y no el usuario.

Módulo puro: sin I/O, sin dependencias fuera de la stdlib.
"""

from __future__ import annotations

import re

from claude_export_md.domain.manifest import split_part_suffix

#: Mismos criterios que `scripts/anonymize_fixture.py`.
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

EMAIL_MARK = "<email>"
UUID_MARK = "<uuid>"


def redact_text(value: str) -> str:
    """Sustituye correos y UUIDs por un marcador. `ana@example.com` → `<email>`."""
    return UUID.sub(UUID_MARK, EMAIL.sub(EMAIL_MARK, value))


def _stem(name: str) -> str:
    head, dot, _ = name.rpartition(".")
    return head if dot and head else name


def _extension(name: str) -> str:
    head, dot, tail = name.rpartition(".")
    return tail.lower() if dot and head else ""


def is_predictable_name(name: str, category: str) -> bool:
    """`True` si el nombre lo decide el formato del export, no el contenido del usuario.

    Predecible = el nombre, sin extensión y sin sufijo de parte, es el de la categoría:
    `conversations.json`, `conversations-001.json`, `users.json`. Todo lo demás
    (`profile.md`, `people/ana.md`, `captura.png`) se considera variable.
    """
    stem = _stem(name)
    guessed = split_part_suffix(stem)
    base = guessed[0] if guessed is not None else stem
    return base.casefold() == category.casefold()


def group_pattern(path: str) -> str:
    """Glob que representa al archivo sin nombrarlo: `a/b/ana.md` → `a/b/*.md`."""
    directory, _, name = path.rpartition("/")
    extension = _extension(name)
    leaf = f"*.{extension}" if extension else "*"
    if not directory:
        return leaf
    return f"{redact_text(directory)}/{leaf}"


def describe_path(path: str, category: str) -> tuple[str | None, str | None]:
    """`(ruta literal, patrón)`: exactamente uno de los dos no es `None`.

    La ruta literal solo se devuelve para nombres predecibles (`is_predictable_name`);
    en cualquier otro caso se devuelve el patrón del grupo al que pertenece el archivo.
    """
    name = path.rpartition("/")[2]
    if is_predictable_name(name, category):
        return redact_text(path), None
    return None, group_pattern(path)


def label_of(path: str, category: str) -> str:
    """Etiqueta redactada de un archivo, para advertencias y logs del inventario."""
    literal, pattern = describe_path(path, category)
    return literal or pattern or path


__all__ = [
    "EMAIL",
    "EMAIL_MARK",
    "UUID",
    "UUID_MARK",
    "describe_path",
    "group_pattern",
    "is_predictable_name",
    "label_of",
    "redact_text",
]
