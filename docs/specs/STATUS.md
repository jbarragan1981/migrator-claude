# STATUS - tablero vivo

Actualizalo al empezar y al cerrar cada tarea. Los hooks leen las lineas "- [ ]" para recordar pendientes.

## M0 - Esqueleto
- [x] Crear estructura del monorepo segun CLAUDE.md 3 (uv workspace + pnpm en apps/web)
- [x] justfile con setup/inventory/convert/test/lint/api/web/up/gen-client
- [ ] CI en verde con paquetes vacios - workflow creado (.github/workflows/ci.yml); just setup/lint/test verificados localmente, falta confirmar la corrida real en GitHub Actions (no se hizo push todavia)
- [x] Comando inventory end-to-end: core (domain/ports/adapters/usecase) + CLI, contra fixtures sinteticos (spec 01, CA-1..CA-8)
- [x] Bloqueantes de la revision: inventario sin nombres de archivo hoja (ADR-0004, CA-7), .coverage ignorado, CLI atrapa ClaudeExportMdError (codigo 2), regex de sufijo de parte que ya no confunde fechas (CA-8)
- [x] Fase 0: correr inventario sobre la carpeta real y documentar las 5 categorias en docs/export-format/ (conversations.md, memories.md, projects.md, frames.md, light_metadata.md - las 5 escritas contra docs/export-format/inventory.json y los fixtures anonimizados existentes)
- [x] Fixtures anonimizados por categoria, incluido manifest (packages/core/tests/fixtures/v2026-batched/{conversations,memories,projects,frames,light_metadata,manifest}/) - generados y regenerados dos veces con scripts/extract_real_samples.py a partir del export real; el fixture de manifest NO va en modo estructura (category/part/batch_index/filename/total_files/version/instructions quedan literales por ser esquema de Anthropic, no datos del usuario - solo se quita export_url)

## M1 - memories + conversations
- [ ] Modelo de dominio (spec 02) - AJUSTAR: Memory ya no asume "carpeta de .md con path original de archivo"; ver docs/export-format/memories.md y 03-parsers.md CA de memories (memory_files[].path real a confirmar, conversations_memory y project_memories necesitan path sintetico)
- [ ] Parser memories + render + snapshot - usar UN SOLO archivo JSON por cuenta, no recorrer carpeta (ver 03-parsers.md)
- [ ] Parser conversations (streaming) + render + artefactos - content[] tiene al menos 4 tipos de bloque confirmados (text, thinking, tool_use, tool_result); ver docs/export-format/conversations.md
- [ ] CLI convert usable end-to-end

## M2 - projects, light_metadata, frames, indices
- [ ] Parser projects - un archivo por proyecto (no array unico); resolver de donde sale el contenido real de docs[] (pregunta abierta, ver abajo)
- [ ] Parser light_metadata - mapea directo a Account
- [ ] Parser frames - confirmar antes donde vive el contenido real del artefacto (pregunta abierta, ver abajo)

## M3 - API + jobs + SSE + Docker
## M4 - Web
## M5 - PyPI, plantillas personalizables, ejecutable

## Decisiones pendientes (para el usuario)
- [ ] Confirmar donde vive el CONTENIDO real de cada artefacto de frames (frames-000/artifacts/<uuid>/*.json solo trae metadata: id, kind, visibility, versions[] con title/description/created_at, pero ningun campo de tipo content/code/body). Ver docs/export-format/frames.md, seccion Dudas.
- [ ] Confirmar donde vive el CONTENIDO de cada doc de un proyecto (projects-000/projects/<uuid>.json -> docs[] solo trae uuid/filename/created_at, sin el texto del doc). Ver docs/export-format/projects.md, seccion Dudas.
- [ ] Confirmar si memory_files[].path (dentro de memories-000/memories/<account_uuid>.json) codifica efectivamente rutas tipo "/profile.md" o "/people/nombre.md" - en el fixture anonimizado el valor esta reemplazado por longitud de cadena y no se puede leer. Ver docs/export-format/memories.md, seccion Dudas.
- [x] RESUELTO: el manifest_path=null de docs/export-format/inventory.json era porque el member-manifest-*.json no estaba todavia en la raiz del export cuando se corrio `just inventory` (el usuario lo ubico despues). No es un bug del detector de manifiesto. Documentado en docs/export-format/manifest.md. Hallazgo real: la clave raiz del manifiesto es `data_files` (no `files/exports/parts/data/items/artifacts` como se habia adivinado antes de la Fase 0). El usuario volvio a correr `just inventory` y el `inventory.json` local ya muestra manifest_path resuelto y missing_categories/missing_parts vacios - ese archivo NO se commitea (esta en .gitignore a proposito, es un artefacto local de exploracion, no un entregable versionado).
- [x] adapters/manifest.py no reconocia la clave raiz real `data_files` del manifiesto (ver arriba) - RESUELTO, `data_files` es ahora la primera clave probada en `_LIST_KEYS`, con test de regresion contra el fixture real.
- [ ] Se publica en PyPI bajo nombre claude-export-md o con prefijo propio?

## Deuda tecnica (revision architect-reviewer, cierre de M0)
- [ ] usecases/inventory.py: si falla la lectura del manifiesto, el nombre real del archivo (con uuid de cuenta) queda sin redactar en `warnings` -> aplicar `redact_text()` al mensaje de la excepcion antes de loguearlo/guardarlo.
- [ ] adapters/manifest.py: el log de `path.name` cuando falla el manifiesto tambien va crudo -> redactar igual que arriba.
- [ ] usecases/inventory.py: los nombres de categoria que vienen del manifiesto (declared_parts) pueden terminar sin redactar en warnings/missing_parts si algun dia una categoria no reconocida trae texto libre - aplicar redact_text() al consumir declared_parts().
- [ ] docs/specs/02-domain-model.md: `Memory` (`path, content, updated_at?, extra`) no tiene campo para asociarse a un Project, pero 03-parsers.md (CA de memories) exige que quede "ligada a ese Project por uuid" via `project_memories`. Contradiccion real a resolver en M1 con un ADR antes de tocar el modelo (spec 02 CA-5 exige ADR para cambiar la lista de entidades) - probablemente `Memory` necesite `project_id: str | None`.
- [ ] Los fixtures reales de v2026-batched/{conversations,memories,projects,frames,light_metadata}/ no los usa ningun test todavia (solo el de manifest) - son documentacion, no red de seguridad; atarlos a tests en M1/M2.
- [ ] `--keep-structure-only` de anonymize_fixture.py rompe integridad referencial entre fixtures (un uuid como valor -> `<str:N>`, como clave -> uuid falso determinista) - para M1 conviene una variante que anonimice valores con forma de uuid/email de forma deterministas (no solo claves), asi se puede probar `conversation.project_uuid -> project.uuid` con datos reales anonimizados.
- [ ] apps/web sigue siendo un stub (scripts/noop-*.cjs); `just lint`/`just test`/CI pasan sin ejercitar nada real del front - normal para M0, dejar constancia para no sorprenderse en M4.
- [ ] CI (.github/workflows/ci.yml) nunca corrio en GitHub Actions todavia, solo se verifico el equivalente local en Windows.
