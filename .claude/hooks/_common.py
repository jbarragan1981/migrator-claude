"""Utilidades compartidas por los hooks. Cross-platform (Windows/macOS/Linux): solo Python estándar."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())).resolve()

# Rutas que contienen datos reales del usuario: nunca se leen, escriben ni borran desde Claude Code.
PROTECTED_DIRS = ("exports", "output")
# Archivos que solo cambian vía herramienta (uv lock / pnpm install), nunca a mano.
LOCKED_FILES = ("uv.lock", "pnpm-lock.yaml", "package-lock.json")
# Dependencias prohibidas dentro de packages/core (regla de arquitectura hexagonal).
CORE_FORBIDDEN_IMPORTS = ("fastapi", "typer", "rich", "uvicorn", "starlette", "requests", "httpx")


def read_input() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def block(msg: str) -> None:
    """Exit code 2 = bloquea la acción y muestra el mensaje a Claude."""
    print(msg, file=sys.stderr)
    sys.exit(2)


def warn(msg: str) -> None:
    """Exit code 0 con stdout = no bloquea; el texto queda como contexto para Claude."""
    print(msg)


def rel(path: str) -> str:
    try:
        return str(Path(path).resolve().relative_to(PROJECT_DIR)).replace("\\", "/")
    except Exception:
        return path.replace("\\", "/")


def is_protected(path: str) -> bool:
    r = rel(path)
    parts = r.split("/")
    return any(p in PROTECTED_DIRS for p in parts) or Path(r).name.startswith(".env")
