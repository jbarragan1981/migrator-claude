"""Inventario crudo del export ANTES de que exista el comando `claude-export-md inventory`.

Uso: python scripts/inventory_raw.py <carpeta_del_export> [--out docs/export-format/inventory.json]

Recorre las subcarpetas (o zips), lista archivos con tamaño y, para cada .json, muestra el tipo raíz,
las claves de primer nivel y las claves de los primeros 3 ítems leyendo en streaming (ijson si está
instalado; si no, lee solo los primeros 2 MB). Nunca imprime valores, solo estructura.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from typing import Any

try:
    import ijson  # type: ignore
except ImportError:  # pragma: no cover
    ijson = None

SAMPLE_ITEMS = 3


def shape(o: Any, depth: int = 0) -> Any:
    if depth > 3:
        return type(o).__name__
    if isinstance(o, dict):
        return {k: shape(v, depth + 1) for k, v in list(o.items())[:40]}
    if isinstance(o, list):
        return [shape(o[0], depth + 1)] if o else []
    return type(o).__name__


def inspect_json(fp) -> dict[str, Any]:  # noqa: ANN001
    head = fp.read(1)
    fp.seek(0)
    info: dict[str, Any] = {"root": "array" if head == b"[" else "object"}
    if ijson is not None:
        if info["root"] == "array":
            items = []
            for i, it in enumerate(ijson.items(fp, "item")):
                items.append(shape(it))
                if i + 1 >= SAMPLE_ITEMS:
                    break
            info["item_shapes"] = items
        else:
            info["top_keys"] = [k for k, _ in ijson.kvitems(fp, "")][:60] if False else "usar ijson.kvitems manualmente"
            fp.seek(0)
            try:
                keys = []
                for prefix, event, _ in ijson.parse(fp):
                    if prefix == "" and event == "map_key":
                        pass
                    if event == "map_key" and prefix == "":
                        keys.append(_)
                    if len(keys) > 60:
                        break
                info["top_keys"] = keys
            except Exception as e:  # noqa: BLE001
                info["error"] = str(e)
    else:
        raw = fp.read(2_000_000)
        try:
            data = json.loads(raw)
            info["shape"] = shape(data)
        except Exception:
            info["note"] = "archivo > 2 MB sin ijson: instala ijson (uv add ijson) para muestrear"
    return info


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else None
    inv: dict[str, Any] = {"root": root.name, "categories": {}}
    for entry in sorted(root.iterdir()):
        cat = entry.name.rsplit("-", 1)[0]
        c = inv["categories"].setdefault(cat, {"parts": [], "files": []})
        c["parts"].append(entry.name)
        if entry.is_dir():
            for f in sorted(entry.rglob("*")):
                if f.is_file():
                    rec: dict[str, Any] = {"path": str(f.relative_to(root)).replace("\\", "/"), "bytes": f.stat().st_size}
                    if f.suffix == ".json":
                        with f.open("rb") as fp:
                            rec["json"] = inspect_json(fp)
                    c["files"].append(rec)
        elif entry.suffix == ".zip":
            with zipfile.ZipFile(entry) as z:
                for zi in z.infolist():
                    rec = {"path": f"{entry.name}!{zi.filename}", "bytes": zi.file_size}
                    if zi.filename.endswith(".json") and ijson is not None:
                        with z.open(zi) as fp:
                            rec["json"] = inspect_json(fp)  # type: ignore[arg-type]
                    c["files"].append(rec)
        elif entry.suffix == ".json":
            c["files"].append({"path": entry.name, "bytes": entry.stat().st_size, "note": "manifiesto"})
    text = json.dumps(inv, ensure_ascii=False, indent=2, sort_keys=True)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"OK → {out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
