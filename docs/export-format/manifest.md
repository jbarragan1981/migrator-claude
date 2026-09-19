# member-manifest-*.json

Versión de formato: batched-manifest (2026)
Archivos: `member-manifest-*.json` en la raíz del export (junto a `conversations-000/`, `memories-000/`, etc.), no dentro de ninguna subcarpeta.
Tamaño observado: pequeño (KB, no MB). Ítems: `total_files` (5 en el export de referencia — una entrada por categoría/parte). Partes: no aplica al manifiesto en sí.

## Estructura

- raíz: objeto
- ítem (raíz):
  - `created_at`: string (timestamp) — obligatorio
  - `version`: string — obligatorio
  - `instructions`: string — obligatorio
  - `total_files`: int — obligatorio
  - `data_files`: array de objetos — obligatorio. **Esta es la clave real que declara las categorías/partes**, no `files`/`exports`/`parts`/`data`/`items`/`artifacts` como se había asumido antes de la Fase 0.
- ítem de `data_files[]`:
  - `category`: string — obligatorio (nombre de categoría, p. ej. `"conversations"`)
  - `part`: int — obligatorio (0 para categorías sin partición observada en este export)
  - `batch_index`: int — obligatorio (índice del archivo dentro del lote; en el export de referencia coincide con el orden de `data_files[]`, no necesariamente con `part`)
  - `filename`: string — obligatorio (nombre del archivo/zip declarado)
  - `export_url`: string — obligatorio en el dato real, **se descarta siempre al parsear** (es de un solo uso y expira; CLAUDE.md §5). Nunca se debe loguear, serializar ni conservar.

## Variantes observadas

Solo se observó un manifiesto (export de referencia, 1 usuario). No hay evidencia todavía de manifiestos con `part > 0` real (el único export inspeccionado no tenía categorías particionadas en más de un archivo).

## Ejemplo (las 5 entradas reales de `data_files`)

`category`, `part`, `batch_index`, `filename`, `total_files`, `version` e `instructions` los elige Anthropic (esquema fijo, no datos del usuario), así que se dejan literales — igual que se documenta cualquier campo de esquema en el resto de este directorio. Lo único que se quita es `export_url` (de un solo uso, expira; CLAUDE.md §5).

```json
{
  "created_at": "2026-09-18T16:59:47.566776+00:00",
  "data_files": [
    { "batch_index": 0, "category": "light_metadata", "filename": "light_metadata-000.zip", "part": 0 },
    { "batch_index": 1, "category": "projects", "filename": "projects-000.zip", "part": 0 },
    { "batch_index": 2, "category": "memories", "filename": "memories-000.zip", "part": 0 },
    { "batch_index": 3, "category": "frames", "filename": "frames-000.zip", "part": 0 },
    { "batch_index": 4, "category": "conversations", "filename": "conversations-000.zip", "part": 0 }
  ],
  "instructions": "Download each file using the export_url. Note: Each export URL can only be used once.",
  "total_files": 5,
  "version": "1.0"
}
```

(fixture completo, con las 5 entradas, en `packages/core/tests/fixtures/v2026-batched/manifest/member-manifest.json`)

## Dudas / no determinable

- No se pudo confirmar si `data_files[].part` alguna vez es > 0 en la práctica (el único export inspeccionado no tenía categorías particionadas). El código debe seguir siendo tolerante a esa posibilidad, no asumir que siempre es 0.
- No se confirmó el formato exacto de `version` ni si cambia entre exports (el fixture anonimizado solo revela que es un string de 3 caracteres, p. ej. podría ser `"1.0"` o similar).
- ~~Impacto en código~~ **RESUELTO**: `packages/core/src/claude_export_md/adapters/manifest.py` (`_LIST_KEYS`) ya reconoce `data_files` como primera clave raíz probada (antes de los alias sin confirmar `files|exports|parts|data|items|artifacts`). Test de regresión contra este fixture real en `packages/core/tests/test_manifest.py::test_real_manifest_fixture_declares_its_entries`.
