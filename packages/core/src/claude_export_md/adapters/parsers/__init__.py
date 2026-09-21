"""Parsers por categoría del export (CLAUDE.md §3).

Un módulo por categoría (`memories`, `conversations`, `projects`, `frames`,
`light_metadata`), cada uno con una función `parse(source, report) -> Iterator[Entidad]`
que lee del puerto `ExportSource` y acumula lo que no pudo parsear en `Report`, sin
lanzar por un ítem (CLAUDE.md §4).
"""

from __future__ import annotations
