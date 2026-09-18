---
name: markdown-template
description: Reglas para crear o cambiar plantillas Jinja2 de salida Markdown (frontmatter, cuerpo, índices) y sus tests de snapshot. Úsalo cuando el usuario pida cambiar cómo se ve un .md generado, agregar un campo al frontmatter, cambiar nombres de archivo o carpetas de salida, o soportar Obsidian/Notion.
---

# Plantillas de salida Markdown

Ubicación: `packages/core/src/claude_export_md/rendering/templates/*.md.j2`. Contrato completo en `docs/specs/04-markdown-output.md` y `docs/output-layout.md`.

## Reglas
1. Frontmatter YAML obligatorio: `id, type, title, created_at, updated_at, source_file, project_id?, tags, extra?`. Fechas ISO-8601 UTC (`2026-09-18T16:59:47Z`).
2. Nada de la corrida actual en el archivo (ni fecha de generación ni versión de la herramienta): eso va en `_report/summary.json`.
3. Nombres de archivo: `YYYY-MM-DD_<slug>_<uuid8>.md`, slug ASCII minúsculas, máx. 60 caracteres, colisiones imposibles gracias al uuid8.
4. Enlaces entre archivos siempre relativos (`../../projects/<slug>/project.md`), para que funcionen en Obsidian, VS Code y GitHub.
5. Texto del usuario/Claude se inserta tal cual (Markdown ya es Markdown). Solo se escapa el frontmatter (YAML) y los `---` al inicio de línea dentro del cuerpo.
6. Bloques `tool_use`/`tool_result` van dentro de `<details><summary>…</summary>` para no ensuciar la lectura.
7. Artefactos (código largo, SVG, HTML) se extraen a `<slug>/artifacts/<n>-<nombre>.<ext>` y se enlazan; no se pegan inline si superan 40 líneas.

## Ciclo
1. Cambia/crea la plantilla.
2. Test de snapshot con `syrupy`: `uv run pytest packages/core/tests/test_render.py --snapshot-update` SOLO tras revisar el diff a ojo y confirmar que el cambio es intencional.
3. Renderiza un fixture completo y abre el resultado en un visor Markdown para verificar.
4. Si el usuario puede sobreescribir la plantilla (`--templates`), documenta las variables disponibles en `docs/specs/04-markdown-output.md`.
