"""PostToolUse(Edit|Write|MultiEdit): formatea y lintea el archivo recién escrito. Nunca bloquea; informa."""
from __future__ import annotations

import shutil
import subprocess

from _common import PROJECT_DIR, read_input, rel, warn

data = read_input()
ti = data.get("tool_input") or {}
path: str = ti.get("file_path") or ti.get("path") or ""
if not path:
    raise SystemExit(0)
r = rel(path)


def run(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=True, text=True, timeout=50)
        return (p.stdout + p.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return f"(no se pudo ejecutar {cmd[0]}: {e})"


if r.endswith(".py") and shutil.which("uv"):
    run(["uv", "run", "ruff", "format", r])
    out = run(["uv", "run", "ruff", "check", "--fix", r])
    if out and "All checks passed" not in out:
        warn(f"[post_edit] ruff en {r}:\n{out}")
    if r.startswith("packages/core/src/"):
        out = run(["uv", "run", "mypy", "--strict", r])
        if out and "Success" not in out:
            warn(f"[post_edit] mypy --strict en {r}:\n{out}")

elif r.startswith("apps/web/") and r.endswith((".ts", ".html", ".scss")) and shutil.which("pnpm"):
    run(["pnpm", "-C", "apps/web", "exec", "prettier", "--write", r.removeprefix("apps/web/")])
    if r.endswith(".ts"):
        out = run(["pnpm", "-C", "apps/web", "exec", "eslint", r.removeprefix("apps/web/")])
        if out:
            warn(f"[post_edit] eslint en {r}:\n{out}")

# Recordatorio de traducciones: si se agregó texto visible en un template Angular sin transloco.
if r.startswith("apps/web/src/") and r.endswith(".html"):
    try:
        text = (PROJECT_DIR / r).read_text(encoding="utf-8")
        if ">" in text and "transloco" not in text and "| t" not in text:
            warn(f"[post_edit] {r} no usa Transloco. Todo texto visible va por es.json/en.json.")
    except Exception:
        pass
