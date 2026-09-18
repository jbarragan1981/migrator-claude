---
name: milestone
description: Orquesta un milestone completo (M0–M5 de CLAUDE.md) delegando a los subagentes en el orden correcto y cerrando con revisión de arquitectura. Úsalo cuando el usuario diga "arranca M1", "cierra el milestone", "avanza con el siguiente hito" o "construye la fase X".
---

# Ejecutar un milestone

## Orden de delegación (no lo alteres)
1. **Planificar**: lee `docs/specs/STATUS.md` y el spec del milestone. Escribe la lista de tareas en STATUS.md antes de tocar código.
2. **Formato** (solo si el milestone toca parsers y falta `docs/export-format/<categoria>.md`): delega a `format-explorer`.
3. **Core**: delega a `core-developer`, una categoría/entidad por invocación, con el spec y el fixture como contexto.
4. **API** (M3+): delega a `api-developer` cuando core exponga la función pública que la API necesita.
5. **Web** (M4+): delega a `web-developer` solo con el cliente OpenAPI ya regenerado.
6. **Release** (cada milestone): delega a `release-engineer` para CI verde y `just up`.
7. **Revisión**: delega a `architect-reviewer` sobre `git diff main...HEAD`. Si hay bloqueantes, vuelve al agente responsable; máximo 2 rondas antes de escalar al usuario.
8. **Cierre**: marca tareas en STATUS.md, actualiza `CHANGELOG.md`, propone el mensaje de commit (Conventional Commits) y resume qué decisiones deberían subir a CLAUDE.md.

## Reglas
- Un commit por tarea coherente, nunca `git add -A`.
- No avances de fase si `just test` no está verde.
- Si un agente necesita datos reales del usuario, detente y pídeselos: nunca los busques en `exports/`.
