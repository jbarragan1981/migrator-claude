# Orquestación — cómo se construye el proyecto con Claude Code

## Piezas y para qué sirve cada una
| Pieza | Ubicación | Rol |
|---|---|---|
| CLAUDE.md | raíz | Constitución del proyecto: reglas, stack, estructura. Se lee en cada sesión. |
| Specs | `docs/specs/` | Qué hay que construir, con criterios de aceptación que se convierten en tests. |
| STATUS.md | `docs/specs/` | Tablero vivo; los hooks leen los `- [ ]`. |
| Skills | `.claude/skills/*/SKILL.md` | Procedimientos repetibles (cómo agregar un parser, una feature Angular, un ADR). Se invocan como `/nombre` o los carga Claude por contexto. |
| Agents | `.claude/agents/*.md` | Especialistas con herramientas acotadas. Claude los delega; `/milestone` los coordina. |
| Hooks | `.claude/settings.json` + `.claude/hooks/*.py` | Guardarraíles deterministas: bloquean lo peligroso, formatean, inyectan contexto. |
| Permissions | `.claude/settings.json` | Lista blanca de comandos habituales y lista negra de destructivos. |

## Flujo de un turno típico
```
SessionStart ──► session_start.py (estado, Fase 0, tareas abiertas)
Prompt ───────► prompt_context.py (recuerda Fase 0 / pendientes)
Claude planea ► lee spec + skill ► delega a agente
  agente edita ► PreToolUse guard_files.py (arquitectura, privacidad) ► PostToolUse post_edit.py (ruff/mypy/prettier)
  agente bash  ► PreToolUse guard_bash.py (rm -rf, pip, exports/, claude.ai)
SubagentStop ─► stop_check.py (lint de lo tocado, fugas de datos)
Stop ─────────► stop_check.py (+ aviso core-sin-tests, domain-sin-ADR)
```

## Cómo arrancar (primer día)
```
# 1) Copia CLAUDE.md, .claude/, docs/ y scripts/ a la raíz del repo vacío.
# 2) Pon tus carpetas extraídas en ./exports/<mi-cuenta>/   (está en .gitignore)
# 3) Abre Claude Code y escribe:
/milestone M0
# 4) Cuando pida la ruta del export para la Fase 0, dale ./exports/<mi-cuenta>
```

## Reglas de delegación
- `format-explorer` antes de cualquier parser; es el único que "mira" el export, y solo estructura.
- `core-developer` una categoría por invocación; TDD.
- `api-developer` y `web-developer` solo cuando core/API ya exponen lo que necesitan.
- `architect-reviewer` antes de cada commit relevante; sus bloqueantes se resuelven antes de seguir.
- `release-engineer` cierra cada milestone con CI verde.

## Qué hacer si un hook bloquea algo legítimo
Léelo: el mensaje dice la regla. Si la regla está mal, cámbiala en `.claude/hooks/*.py` y documenta por qué en un ADR. No desactives el hook desde el prompt.
