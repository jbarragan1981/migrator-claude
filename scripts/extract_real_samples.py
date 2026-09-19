"""Extrae 2-3 ítems representativos POR CATEGORÍA de un export real de Claude.ai
y los anonimiza en modo estructura (toda cadena -> "<str:len>", ver
anonymize_fixture.py --keep-structure-only) antes de escribirlos como fixtures.

Nunca imprime valores del export: solo conteos, tamaños y nombres de archivo
generados por el propio script. Solo biblioteca estándar + ijson (ya instalado
como dependencia de packages/core). Nunca se ejecuta sobre exports/ desde
Claude Code: córrelo tú a mano con `uv run python ...` para tener ijson en el
PATH del intérprete.

Uso:
    uv run python scripts/extract_real_samples.py <carpeta_export> \
        [--out packages/core/tests/fixtures/v2026-batched] [--max-items 3]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import anonymize_fixture as af  # noqa: E402

try:
    import ijson  # type: ignore
except ImportError:  # pragma: no cover
    ijson = None

MAX_ITEMS = 3


def truncate_lists(obj: Any, max_items: int) -> Any:
    if isinstance(obj, dict):
        return {k: truncate_lists(v, max_items) for k, v in obj.items()}
    if isinstance(obj, list):
        return [truncate_lists(v, max_items) for v in obj[:max_items]]
    return obj


def anon(obj: Any) -> Any:
    return af.walk(truncate_lists(obj, MAX_ITEMS), structure_only=True)


def write_fixture(out_dir: Path, category: str, name: str, data: Any) -> None:
    dest = out_dir / category
    dest.mkdir(parents=True, exist_ok=True)
    (dest / name).write_text(
        json.dumps(anon(data), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def sample_conversations(root: Path, out_dir: Path) -> int:
    fp = root / "conversations-000" / "conversations.json"
    if not fp.exists() or ijson is None:
        return 0
    items: list[Any] = []
    with fp.open("rb") as f:
        for i, item in enumerate(ijson.items(f, "item")):
            items.append(item)
            if i + 1 >= MAX_ITEMS:
                break
    if items:
        write_fixture(out_dir, "conversations", "conversations.json", items)
    return len(items)


def sample_glob(root: Path, out_dir: Path, category: str, pattern: str) -> int:
    files = sorted(root.glob(pattern))[:MAX_ITEMS]
    count = 0
    for i, f in enumerate(files, start=1):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        write_fixture(out_dir, category, f"sample-{i:02d}.json", data)
        count += 1
    return count


def sample_memories(root: Path, out_dir: Path) -> int:
    memories_dir = root / "memories-000" / "memories"
    files = sorted(memories_dir.glob("*.json")) if memories_dir.exists() else []
    if not files:
        return 0
    data = json.loads(files[0].read_text(encoding="utf-8"))
    # Nombre genérico: el nombre real del archivo es el account_uuid del usuario.
    write_fixture(out_dir, "memories", "memories.json", data)
    return 1


def sanitize_manifest(data: Any) -> Any:
    """El manifiesto no es contenido del usuario: category/part/batch_index/
    filename/total_files/version/instructions/created_at los elige Anthropic
    (misma idea que domain/redaction.py::is_predictable_name), así que se
    conservan literales para que el fixture sirva para probar el parser real.
    Lo único que se quita es export_url (de un solo uso, expira, CLAUDE.md §5).
    Nunca se trunca: el manifiesto real sirve justamente para validar que
    están TODAS las categorías/partes declaradas.
    """
    if isinstance(data, dict):
        out = dict(data)
        if "data_files" in out and isinstance(out["data_files"], list):
            out["data_files"] = [
                {k: v for k, v in entry.items() if k != "export_url"}
                if isinstance(entry, dict)
                else entry
                for entry in out["data_files"]
            ]
        return out
    return data


def sample_manifest(root: Path, out_dir: Path) -> str | None:
    matches = sorted(root.glob("member-manifest-*.json"))
    if not matches:
        return None
    data = sanitize_manifest(json.loads(matches[0].read_text(encoding="utf-8")))
    dest = out_dir / "manifest"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "member-manifest.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return matches[0].name


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    root = Path(sys.argv[1]).resolve()
    out_dir = Path("packages/core/tests/fixtures/v2026-batched")
    if "--out" in sys.argv:
        out_dir = Path(sys.argv[sys.argv.index("--out") + 1])
    if "--max-items" in sys.argv:
        global MAX_ITEMS
        MAX_ITEMS = int(sys.argv[sys.argv.index("--max-items") + 1])

    counts = {
        "conversations": sample_conversations(root, out_dir),
        "frames": sample_glob(root, out_dir, "frames", "frames-000/artifacts/*/*.json"),
        "light_metadata": sample_glob(root, out_dir, "light_metadata", "light_metadata-000/*.json"),
        "projects": sample_glob(root, out_dir, "projects", "projects-000/projects/*.json"),
        "memories": sample_memories(root, out_dir),
    }
    manifest_name = sample_manifest(root, out_dir)

    print(f"Fixtures anonimizados (modo estructura-only) escritos en: {out_dir}")
    for cat, n in counts.items():
        print(f"  {cat}: {n} ítem(s)")
    if manifest_name:
        print(f"  manifest: encontrado -> {manifest_name}")
    else:
        print("  manifest: NO encontrado en la raíz del export (member-manifest-*.json)")


if __name__ == "__main__":
    main()
