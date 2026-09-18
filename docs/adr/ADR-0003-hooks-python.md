# ADR-0003: Hooks de Claude Code en Python, no en bash
Fecha: 2026-09-18   Estado: Aceptada
## Contexto
El desarrollo ocurre en Windows 11 y el proyecto debe poder construirse igual en macOS/Linux. Los hooks de Claude Code ejecutan un comando de shell; los scripts bash dependen de Git Bash/WSL.
## Decisión
Cada hook es `python .claude/hooks/<nombre>.py`, con solo biblioteca estándar, leyendo el JSON por stdin y usando exit code 2 para bloquear. Se configuran únicamente en `.claude/settings.json` (no en frontmatter de agentes, cuya ejecución para subagentes ha tenido bugs reportados).
## Consecuencias
+ Mismo comportamiento en los tres sistemas; fácil de testear con `echo '{...}' | python hook.py`.
- Requiere Python en el PATH como `python` (en macOS/Linux crear alias o usar `python3` en settings.json).
