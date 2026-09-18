# 04 — Salida Markdown

## Objetivo
Un árbol de archivos `.md` navegable en Obsidian, VS Code y GitHub, autocontenido, determinista y con enlaces relativos.

## Árbol (contrato)
Ver `docs/output-layout.md` (copia de la sección 5 de CLAUDE.md). Resumen:
```
output/{README.md, _index.md, _report/, account/, memories/, projects/<slug>/, conversations/YYYY/MM/, frames/}
```

## Frontmatter (todas las entidades)
`id, type, title, created_at, updated_at, source_file, project_id?, tags[], extra?` — ISO-8601 UTC.

## Criterios de aceptación
- **CA-1** Dado un fixture de 3 conversaciones, cuando convierto dos veces, entonces `diff -r` entre ambas salidas está vacío.
- **CA-2** Cada `.md` tiene frontmatter YAML válido (parseable con `python-frontmatter`) con los campos obligatorios.
- **CA-3** Conversación con mensajes `human`/`assistant` renderiza encabezados `## 👤 Usuario` / `## 🤖 Claude` con timestamp `HH:MM`.
- **CA-4** Un bloque `tool_use` se renderiza dentro de `<details>` y no rompe el Markdown circundante.
- **CA-5** Un artefacto de 120 líneas se escribe en `artifacts/01-<slug>.<ext>` y el cuerpo contiene un enlace relativo a él.
- **CA-6** Título con caracteres no ASCII ("Análisis Ñandú / Q3") produce slug `analisis-nandu-q3`.
- **CA-7** `_index.md` lista todas las conversaciones ordenadas por fecha descendente con enlace relativo, proyecto y nº de mensajes.
- **CA-8** `_report/summary.json` contiene conteos por categoría y nº de errores; `errors.jsonl` una línea por `ParseError`.
- **CA-9** Con `--templates ./mis-plantillas`, una plantilla sobreescrita reemplaza a la default y las demás siguen funcionando.
- **CA-10** El cuerpo del `.md` nunca contiene la fecha de generación ni la versión de la herramienta.
