# 01 — Inventario del export

## Objetivo
Dado un directorio (carpetas extraídas, zips o manifiesto + zips), producir un `Inventory` que describa qué hay, en qué versión de formato, y con qué estructura, sin cargar archivos completos en memoria.

## Alcance
- Detectar versión: `batched-manifest` (2026: `member-manifest-*.json` + `<categoria>-NNN.zip`) o `legacy-single-zip` (`conversations.json`, `projects.json`, `users.json` en un zip).
- Por categoría: archivos, tamaño, nº de partes, tipo raíz, claves de primer nivel, muestra de claves de ítem (primeros 3 ítems), nº aproximado de ítems.
- Validar contra el manifiesto: categorías faltantes, partes faltantes.
- Salida JSON serializable + resumen legible.

## Privacidad del inventario (ADR-0004)
`inventory.json` se comparte (se pega en una issue, se guarda en `docs/export-format/`), así que **no puede contener ningún nombre elegido por el contenido del usuario**:
- Se conserva el nombre de archivo literal SOLO cuando es predecible, es decir cuando el nombre —sin extensión y sin sufijo de parte— coincide con la categoría: `conversations-000/conversations.json`, `conversations-001.json`, `users.json`.
- Cualquier otro nombre hoja (categorías que son carpeta de Markdown, como `memories`, o de adjuntos, como `frames`) se colapsa en patrón + conteo: `{"pattern": "memories-000/people/*.md", "count": 37}`. Nunca aparece `people/<persona>.md`.
- `CategoryInventory.file_count` es el nº real de archivos; `len(files)` es el nº de entradas (archivos + grupos).
- Las claves muestreadas (`top_keys`, claves del `shape`), el nombre del manifiesto y las advertencias pasan por la misma redacción: lo que tenga forma de UUID o de correo sale como `<uuid>` / `<email>`.
- Se conservan los nombres de carpeta (`people/`, `areas/`) porque describen la estructura del export, no al usuario; si una carpeta tuviera forma de UUID/correo también se enmascara.
Red de seguridad adicional: `docs/export-format/inventory.json` está en `.gitignore`.

## Fuera de alcance
Descargar `export_url`; parsear contenido; escribir Markdown.

## Criterios de aceptación
- **CA-1** Dado un directorio con las 5 carpetas extraídas, cuando corro `inventory`, entonces obtengo `format_version="batched-manifest"` y 5 categorías con `parts=[0]`.
- **CA-2** Dado el mismo directorio sin `frames-000`, entonces `missing_categories=["frames"]` y el comando termina con código 0 y una advertencia (no error).
- **CA-3** Dado un `conversations.json` de 800 MB, cuando corro `inventory`, entonces el pico de memoria es < 200 MB (se usa `ijson`, se leen ≤ 3 ítems).
- **CA-4** Dado un zip sin extraer, entonces el inventario lo lee sin extraerlo a disco (`zipfile` + stream).
- **CA-5** Dado un manifiesto que declara `part: 1` para `conversations` y solo existe `conversations-000`, entonces `missing_parts={"conversations":[1]}`.
- **CA-6** El JSON de salida es estable entre corridas (claves ordenadas, sin timestamps de la corrida).
- **CA-7** Dado `memories-000/people/ana-real.md`, el JSON del inventario NO contiene `ana-real` y sí contiene `{"pattern": "memories-000/people/*.md", "count": 1}`.
- **CA-8** El sufijo de parte se reconoce con ceros a la izquierda y 3–6 dígitos (`-000`…`-000000`); `claude-export-2026-02-01.zip` no se interpreta como parte.

## Dependencias
Ninguna (primer módulo de core).

## Riesgos
Formato no documentado por Anthropic → el inventario es precisamente la herramienta para descubrirlo; nunca asumir nombres de archivo.
