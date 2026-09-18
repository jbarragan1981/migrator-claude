"""PreToolUse(Bash): bloquea comandos peligrosos o que rompen las reglas del proyecto."""
from __future__ import annotations

import re

from _common import block, read_input

data = read_input()
cmd: str = (data.get("tool_input") or {}).get("command", "")

RULES: list[tuple[str, str]] = [
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r|\bRemove-Item\b.*-Recurse", "Borrado recursivo bloqueado. Borra archivos puntuales o hazlo tú manualmente."),
    (r"\b(exports|output)[/\\]", "Estás tocando la carpeta exports/ u output/ (datos reales del usuario). Usa tests/fixtures/ anonimizados."),
    (r"git\s+push\s+(-f|--force)", "Push forzado bloqueado."),
    (r"git\s+reset\s+--hard", "git reset --hard bloqueado: podría destruir trabajo no commiteado."),
    (r"\bpip\s+install\b", "Usa `uv add <paquete>` en el paquete correcto, no pip install (rompe el workspace y el lockfile)."),
    (r"claude\.ai/export", "Los export_url del manifiesto son de un solo uso y expiran. La app nunca los descarga."),
    (r"(curl|wget|Invoke-WebRequest).*(api\.anthropic|claude\.ai)", "Sin llamadas de red a Anthropic/Claude desde el proyecto: todo se procesa en local."),
    (r"\bgit\s+add\s+(-A|\.|--all)\b", "No hagas `git add -A`. Agrega archivos por nombre para no colar exports, output o .env."),
]

for pattern, msg in RULES:
    if re.search(pattern, cmd, flags=re.IGNORECASE):
        block(f"[guard_bash] {msg}\nComando: {cmd}")
