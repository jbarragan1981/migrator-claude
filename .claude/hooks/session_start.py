"""SessionStart: resumen del estado del repo al abrir Claude Code."""
from __future__ import annotations

import subprocess

from _common import PROJECT_DIR, warn

out: list[str] = ["[claude-export-md] Estado al iniciar sesión:"]

inv = PROJECT_DIR / "docs" / "export-format" / "inventory.json"
out.append(f"- Fase 0 (inventario del formato): {'HECHA' if inv.exists() else 'PENDIENTE → empezar por aquí'}")

try:
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=PROJECT_DIR, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_DIR, capture_output=True, text=True).stdout.strip()
    out.append(f"- Rama: {branch or '?'} | Cambios sin commit: {len(dirty.splitlines()) if dirty else 0}")
except Exception:
    pass

status = PROJECT_DIR / "docs" / "specs" / "STATUS.md"
if status.exists():
    todo = [l[6:] for l in status.read_text(encoding="utf-8").splitlines() if l.startswith("- [ ]")]
    out.append(f"- Tareas abiertas en STATUS.md: {len(todo)}" + (f" (siguiente: {todo[0]})" if todo else ""))

out.append("- Reglas: leer CLAUDE.md; specs en docs/specs/; nunca tocar exports/ ni output/.")
warn("\n".join(out))
