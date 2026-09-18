---
name: add-parser
description: Checklist TDD para agregar o modificar el parser de una categoría del export (conversations, memories, projects, frames, light_metadata) en packages/core. Úsalo cuando el usuario pida "parsea X", "agrega soporte para X", "el parser de X falla", "soporta la versión legacy".
---

# Agregar / modificar un parser

Precondición: existe `docs/export-format/<categoria>.md` y un fixture anonimizado. Si no, primero el skill `export-format` (o el agente `format-explorer`).

## Checklist (en este orden)
1. **Modelo de dominio** — `packages/core/src/claude_export_md/domain/<entidad>.py`: pydantic v2, `ConfigDict(extra="allow", frozen=True)`, todos los campos opcionales salvo `id`. Fechas como `datetime` aware (UTC).
2. **Test primero** — `packages/core/tests/test_parse_<categoria>.py`:
   - parsea el fixture y devuelve N entidades;
   - conserva campos desconocidos en `extra`;
   - un ítem corrupto genera `ParseError` en `Report.errors` y no detiene el resto;
   - con varias `part`, concatena y no duplica;
   - orden de salida estable.
3. **Parser** — `adapters/parsers/<categoria>.py` exponiendo `def parse(source: ExportSource, report: Report) -> Iterator[Entidad]`. Archivos grandes con `ijson.items(f, "item")`. Sin `print`, sin `datetime.now()`.
4. **Registro** — añade la categoría al registro de parsers en `usecases/convert.py` y al detector de formato en `usecases/inventory.py`.
5. **Render** — si la entidad es nueva, skill `markdown-template`.
6. **Calidad** — `uv run ruff check --fix && uv run ruff format && uv run mypy --strict packages/core && uv run pytest packages/core -q --cov`.
7. **Docs** — actualiza `docs/specs/03-parsers.md` (criterios cumplidos) y `docs/specs/STATUS.md`.

## Errores comunes
- Asumir que `text` existe: en mensajes recientes el contenido está en `content[]` con bloques tipados; `text` puede estar vacío.
- Asumir `sender ∈ {human, assistant}`: valida y conserva el valor original si es otro.
- Usar `json.load` "porque el fixture es pequeño": el parser debe funcionar con el archivo real de cientos de MB.
