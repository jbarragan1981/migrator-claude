# ADR-0004: El inventario nunca expone nombres de archivo variables
Fecha: 2026-09-18   Estado: Aceptada
## Contexto
`Inventory` se escribe en `docs/export-format/inventory.json`, un archivo que el usuario comparte y que el repo versiona. Con `FileInventory.path` guardando la ruta completa de cada archivo hoja, un export real de `memories-000/` (CLAUDE.md §3: `/people/*.md`) filtraría los nombres reales de las personas de las memorias del usuario; lo mismo vale para cualquier categoría que resulte ser una carpeta de archivos con nombre libre (p. ej. `frames`). El inventario describe FORMA, no contenido: un nombre de archivo derivado del contenido es contenido.
## Decisión
1. Una entrada de `FileInventory` es o bien **un archivo nombrable** (`path`) o bien **un grupo de archivos** (`pattern` + `count`). Se conserva el nombre literal solo cuando es predecible: el stem del archivo, sin su sufijo de parte, coincide con la categoría (`conversations-000/conversations.json`, `conversations-001.json`, `users.json`). Cualquier otro nombre hoja se colapsa en un glob por carpeta y extensión: `memories-000/people/*.md` con `count: 37`.
2. `CategoryInventory.file_count` pasa a ser el número real de archivos (los grupos cuentan por `count`), porque `len(files)` ya no lo es.
3. Las claves muestreadas (`top_keys` y las claves de `shape`) que tengan forma de UUID o de correo se sustituyen por `<uuid>` / `<email>` (mismos criterios que `scripts/anonymize_fixture.py`).
4. Las advertencias y `manifest_path` usan la misma etiqueta redactada, porque también viajan dentro del JSON.
## Alternativas consideradas
- Dejar la ruta y avisar al usuario de que no la commitee — depende de la disciplina humana; la fuga es irreversible una vez en git.
- Hashear el nombre hoja — sigue siendo un identificador estable por persona y no aporta nada al objetivo (descubrir el formato).
- Redactar solo la categoría `memories` — el nombre de las categorías no está garantizado y `frames` es aún desconocido; la regla se aplica por forma del nombre, no por lista.
## Consecuencias
+ Un `inventory.json` de un export real es publicable tal cual.
+ La estructura de carpetas (lo que importa para la Fase 0) se conserva: `people/*.md`, `areas/*.md`, `*.png`.
— `Inventory` deja de servir para localizar un archivo concreto; quien necesite abrirlo usa `ExportSource.files()`, que sí trae la ruta real y nunca se serializa.
— `FileInventory.path` pasa a ser `str | None`: los consumidores usan `FileInventory.label`.
