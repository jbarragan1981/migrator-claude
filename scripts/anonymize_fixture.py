"""Anonimiza un JSON del export para usarlo como fixture de test.

Uso: python scripts/anonymize_fixture.py entrada.json salida.json [--keep-structure-only]

- Correos → user<N>@example.com (mismo correo → mismo N)
- UUIDs → uuid determinista derivado (mismo uuid → mismo reemplazo, se conservan las relaciones)
- URLs → https://example.com/<hash corto>
- Cadenas largas (texto de conversaciones) → texto lorem con la misma longitud aproximada
- Con --keep-structure-only, TODA cadena se reemplaza por "<str:len>" (útil para documentar estructura)
Solo biblioteca estándar. Nunca se ejecuta sobre exports/ desde Claude Code: córrelo tú a mano.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import uuid
from pathlib import Path

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
URL = re.compile(r"https?://\S+")
LOREM = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor "
         "incididunt ut labore et dolore magna aliqua ").split()

_emails: dict[str, str] = {}


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def anon_email(m: re.Match[str]) -> str:
    e = m.group(0).lower()
    if e not in _emails:
        _emails[e] = f"user{len(_emails) + 1}@example.com"
    return _emails[e]


def anon_uuid(m: re.Match[str]) -> str:
    return str(uuid.UUID(_h(m.group(0))[:32]))


def anon_url(m: re.Match[str]) -> str:
    return f"https://example.com/{_h(m.group(0))[:10]}"


def lorem(n_chars: int) -> str:
    out: list[str] = []
    total = 0
    i = 0
    while total < n_chars:
        w = LOREM[i % len(LOREM)]
        out.append(w)
        total += len(w) + 1
        i += 1
    return " ".join(out)


def anon_str(s: str, structure_only: bool) -> str:
    if structure_only:
        return f"<str:{len(s)}>"
    s = EMAIL.sub(anon_email, s)
    s = UUID.sub(anon_uuid, s)
    s = URL.sub(anon_url, s)
    if len(s) > 60 and " " in s:  # texto libre: probablemente contenido de conversación
        return lorem(len(s))
    return s


def walk(o: object, structure_only: bool) -> object:
    if isinstance(o, dict):
        return {k: walk(v, structure_only) for k, v in o.items()}
    if isinstance(o, list):
        return [walk(v, structure_only) for v in o]
    if isinstance(o, str):
        return anon_str(o, structure_only)
    return o


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    structure_only = "--keep-structure-only" in sys.argv
    data = json.loads(src.read_text(encoding="utf-8"))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(walk(data, structure_only), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"OK → {dst} ({len(_emails)} correos anonimizados)")


if __name__ == "__main__":
    main()
