"""UserPromptSubmit: inyecta el estado del proyecto para que Claude no se salte la Fase 0 ni el spec vigente."""
from __future__ import annotations

from _common import PROJECT_DIR, read_input, warn

data = read_input()
prompt: str = (data.get("prompt") or "").lower()

inventory = PROJECT_DIR / "docs" / "export-format" / "inventory.json"
status = PROJECT_DIR / "docs" / "specs" / "STATUS.md"

notes: list[str] = []
if not inventory.exists() and any(k in prompt for k in ("parser", "parsear", "convert", "markdown", "conversations", "memories", "projects", "frames")):
    notes.append("FASE 0 PENDIENTE: no existe docs/export-format/inventory.json. Antes de escribir parsers ejecuta `just inventory <carpeta>` y documenta el formato (skill: export-format).")

if status.exists():
    try:
        lines = [l for l in status.read_text(encoding="utf-8").splitlines() if l.startswith("- [ ]")][:3]
        if lines:
            notes.append("Pendientes en STATUS.md: " + " | ".join(l[6:] for l in lines))
    except Exception:
        pass

if notes:
    warn("[contexto del proyecto] " + "\n".join(notes))
