# STATUS — tablero vivo

Actualízalo al empezar y al cerrar cada tarea. Los hooks leen las líneas `- [ ]` para recordar pendientes.

## M0 — Esqueleto
- [ ] Crear estructura del monorepo según CLAUDE.md §3 (uv workspace + pnpm en apps/web)
- [ ] justfile con setup/inventory/convert/test/lint/api/web/up/gen-client
- [ ] CI en verde con paquetes vacíos
- [ ] Fase 0: correr inventario sobre la carpeta real y documentar las 5 categorías en docs/export-format/
- [ ] Fixtures anonimizados por categoría

## M1 — memories + conversations
- [ ] Modelo de dominio (spec 02)
- [ ] Parser memories + render + snapshot
- [ ] Parser conversations (streaming) + render + artefactos
- [ ] CLI convert usable end-to-end

## M2 — projects, light_metadata, frames, índices
## M3 — API + jobs + SSE + Docker
## M4 — Web
## M5 — PyPI, plantillas personalizables, ejecutable

## Decisiones pendientes (para el usuario)
- [ ] Confirmar qué contiene `frames-000` (Fase 0)
- [ ] ¿Se publica en PyPI bajo nombre `claude-export-md` o con prefijo propio?
