"""Stop / SubagentStop: verificación rápida antes de dar por terminado un turno.
No corre la suite completa (eso es `just test`); corre solo lint sobre lo modificado y avisa de riesgos."""
from __future__ import annotations

import subprocess
import sys

from _common import PROJECT_DIR, block, read_input, warn

data = read_input()
if data.get("stop_hook_active"):
    raise SystemExit(0)  # evita bucles: ya estamos continuando por un hook de stop

subagent = "--subagent" in sys.argv


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=PROJECT_DIR, capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return ""


changed = [l.split()[-1] for l in git("status", "--porcelain").splitlines() if l.strip()]
if not changed:
    raise SystemExit(0)

# 1) Nunca dejar datos reales en staging.
leaks = [f for f in changed if f.startswith(("exports/", "output/")) or f.endswith(".env") or f.endswith(".zip")]
if leaks:
    block(f"[stop_check] Hay archivos de datos reales en el árbol de trabajo: {leaks}. Quítalos del staging (git restore --staged) antes de terminar.")

# 2) Lint rápido de los .py tocados.
py = [f for f in changed if f.endswith(".py") and not f.startswith(".claude/")]
if py:
    p = subprocess.run(["uv", "run", "ruff", "check", *py], cwd=PROJECT_DIR, capture_output=True, text=True)
    if p.returncode != 0:
        block(f"[stop_check] ruff reporta errores en archivos modificados. Corrígelos antes de cerrar el turno:\n{p.stdout}")

# 3) Código en core sin test correspondiente.
core_src = [f for f in changed if f.startswith("packages/core/src/") and f.endswith(".py") and "__init__" not in f]
tests = [f for f in changed if "/tests/" in f]
if core_src and not tests and not subagent:
    warn(f"[stop_check] Modificaste core ({len(core_src)} archivo/s) sin tocar tests. CLAUDE.md pide test antes que parser. Confirma que ya existe cobertura o agrégala.")

# 4) Cambios de comportamiento sin ADR/spec.
arch = [f for f in changed if f.startswith(("packages/core/src/claude_export_md/ports", "packages/core/src/claude_export_md/domain"))]
if arch and not any(f.startswith("docs/") for f in changed):
    warn("[stop_check] Cambiaste ports/ o domain/ sin actualizar docs/specs ni docs/adr. Documenta la decisión.")
