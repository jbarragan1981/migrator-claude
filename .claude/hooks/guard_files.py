"""PreToolUse(Edit|Write|MultiEdit): protege rutas y valida reglas de arquitectura ANTES de escribir."""
from __future__ import annotations

import re

from _common import CORE_FORBIDDEN_IMPORTS, LOCKED_FILES, block, is_protected, read_input, rel

data = read_input()
ti = data.get("tool_input") or {}
path: str = ti.get("file_path") or ti.get("path") or ""
content: str = ti.get("content") or ti.get("new_string") or ""

if not path:
    raise SystemExit(0)

r = rel(path)

if is_protected(path):
    block(f"[guard_files] {r} está en una carpeta protegida (exports/, output/ o .env). Datos reales del usuario: prohibido.")

if r.split("/")[-1] in LOCKED_FILES:
    block(f"[guard_files] {r} se regenera con la herramienta (uv lock / pnpm install), no se edita a mano.")

# Regla hexagonal: core no importa frameworks.
if r.startswith("packages/core/src/") and r.endswith(".py"):
    for mod in CORE_FORBIDDEN_IMPORTS:
        if re.search(rf"^\s*(from|import)\s+{mod}\b", content, flags=re.MULTILINE):
            block(f"[guard_files] packages/core no puede importar `{mod}`. core es una librería pura; eso va en apps/api o apps/cli.")
    if re.search(r"^\s*print\(", content, flags=re.MULTILINE):
        block("[guard_files] Sin print() en core. Usa logging.getLogger(__name__).")
    if "datetime.now(" in content or "datetime.utcnow(" in content:
        block("[guard_files] Sin datetime.now()/utcnow() en core: la salida debe ser determinista (mismo export → mismos archivos).")
    if re.search(r"json\.load\(", content) and "conversations" in r:
        block("[guard_files] conversations.json se lee en streaming con ijson, nunca con json.load().")

# Fixtures: detectar datos reales sin anonimizar.
if "/tests/fixtures/" in r:
    if re.search(r"[\w.+-]+@(?!example\.com)[\w-]+\.[\w.]+", content):
        block("[guard_files] El fixture contiene un correo real. Anonimiza con scripts/anonymize_fixture.py (solo @example.com).")
    if re.search(r"https://claude\.ai/export/", content):
        block("[guard_files] El fixture contiene un export_url real. Reemplázalo por https://example.com/export/…")

# Front: sin lógica de parseo ni `any`.
if r.startswith("apps/web/src/") and r.endswith(".ts"):
    if re.search(r":\s*any\b|<any>|as any\b", content):
        block("[guard_files] `any` prohibido en apps/web. Usa los tipos del cliente generado (core/api).")
    if re.search(r"JSON\.parse\(.*conversation", content, flags=re.IGNORECASE):
        block("[guard_files] El front no parsea el export. Eso vive en packages/core; el front solo consume la API.")
