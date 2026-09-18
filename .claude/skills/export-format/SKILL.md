---
name: export-format
description: Procedimiento para inventariar y documentar el formato real de la exportación de Claude.ai (Fase 0) sin exponer datos reales. Úsalo antes de escribir cualquier parser, cuando aparezca una categoría nueva o un archivo con estructura distinta, o cuando el usuario diga "mira qué trae el export", "qué campos tiene conversations", "documenta el formato".
---

# Inventariar el formato del export

## Cuándo
- No existe `docs/export-format/<categoria>.md` para la categoría que se va a parsear.
- Un parser falla contra datos reales del usuario.
- El manifiesto trae `part > 0` para alguna categoría y no está documentado cómo se dividen.

## Pasos
1. Pide la ruta a la carpeta extraída (o a los zips). No aceptes URLs de `claude.ai/export`: son de un solo uso y expiran.
2. Corre `just inventory <ruta>` (o `uv run claude-export-md inventory <ruta> --out docs/export-format/inventory.json`). Si el comando aún no existe, usa `scripts/inventory_raw.py` (una pasada con `ijson`, `head -c`, tamaños, conteo).
3. Lee `inventory.json` y responde por categoría: ¿archivo JSON o carpeta de .md? ¿raíz array u objeto? ¿claves de primer nivel? ¿claves de los ítems y de `chat_messages[0].content[0]`? ¿campos que a veces faltan?
4. Escribe `docs/export-format/<categoria>.md` con la plantilla de abajo.
5. Genera fixture: elige 2–3 ítems representativos (uno "completo", uno "mínimo", uno "raro"), pásalos por `python scripts/anonymize_fixture.py in.json out.json`, guarda en `packages/core/tests/fixtures/<version>/<categoria>/`.
6. Actualiza `docs/specs/03-parsers.md` (criterios de aceptación) y marca la tarea en `docs/specs/STATUS.md`.

## Plantilla de `docs/export-format/<categoria>.md`
```
# <categoria>
Versión de formato: batched-manifest (2026) | legacy-single-zip
Archivos: <lista>   Tamaño observado: <MB>   Ítems: <n>   Partes: <n>
## Estructura
- raíz: array | objeto {clave: ...}
- ítem: { campo: tipo (obligatorio|opcional, % presente), ... }
## Variantes observadas
- ...
## Ejemplo anonimizado (1 ítem)
```json
{...}
```
## Dudas / no determinable
- ...
```

## Prohibido
- Copiar texto real de conversaciones, nombres, correos o uuids reales a docs o fixtures.
- Cargar `conversations.json` completo en memoria.
