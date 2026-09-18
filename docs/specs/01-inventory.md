# 01 — Inventario del export

## Objetivo
Dado un directorio (carpetas extraídas, zips o manifiesto + zips), producir un `Inventory` que describa qué hay, en qué versión de formato, y con qué estructura, sin cargar archivos completos en memoria.

## Alcance
- Detectar versión: `batched-manifest` (2026: `member-manifest-*.json` + `<categoria>-NNN.zip`) o `legacy-single-zip` (`conversations.json`, `projects.json`, `users.json` en un zip).
- Por categoría: archivos, tamaño, nº de partes, tipo raíz, claves de primer nivel, muestra de claves de ítem (primeros 3 ítems), nº aproximado de ítems.
- Validar contra el manifiesto: categorías faltantes, partes faltantes.
- Salida JSON serializable + resumen legible.

## Fuera de alcance
Descargar `export_url`; parsear contenido; escribir Markdown.

## Criterios de aceptación
- **CA-1** Dado un directorio con las 5 carpetas extraídas, cuando corro `inventory`, entonces obtengo `format_version="batched-manifest"` y 5 categorías con `parts=[0]`.
- **CA-2** Dado el mismo directorio sin `frames-000`, entonces `missing_categories=["frames"]` y el comando termina con código 0 y una advertencia (no error).
- **CA-3** Dado un `conversations.json` de 800 MB, cuando corro `inventory`, entonces el pico de memoria es < 200 MB (se usa `ijson`, se leen ≤ 3 ítems).
- **CA-4** Dado un zip sin extraer, entonces el inventario lo lee sin extraerlo a disco (`zipfile` + stream).
- **CA-5** Dado un manifiesto que declara `part: 1` para `conversations` y solo existe `conversations-000`, entonces `missing_parts={"conversations":[1]}`.
- **CA-6** El JSON de salida es estable entre corridas (claves ordenadas, sin timestamps de la corrida).

## Dependencias
Ninguna (primer módulo de core).

## Riesgos
Formato no documentado por Anthropic → el inventario es precisamente la herramienta para descubrirlo; nunca asumir nombres de archivo.
