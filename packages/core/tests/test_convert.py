"""Caso de uso `convert`: el árbol completo de la salida (spec 04 CA-1/CA-7/CA-8).

El fixture es el de `memories` más el de `conversations`, copiados a una misma raíz:
así se ejercita lo que hará el usuario (un export con varias categorías) sin duplicar
los datos sintéticos que ya viven en `fixtures/synthetic/`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import write_manifest

from claude_export_md.adapters.sink_filesystem import FilesystemSink
from claude_export_md.adapters.source_folder import FolderSource
from claude_export_md.errors import OutputNotEmptyError, UnknownFormatError
from claude_export_md.ports.sink import MarkdownSink
from claude_export_md.usecases.convert import ConvertResult, convert

#: Fecha del manifiesto sintético: es la que debe aparecer en el README (CLAUDE.md §1.4).
EXPORT_CREATED_AT = "2026-09-18T16:59:47.566776+00:00"


class RecordingSink:
    """`MarkdownSink` en memoria: prueba la orquestación de `convert` sin tocar disco."""

    def __init__(self, writable: bool = True) -> None:
        self.files: dict[str, str] = {}
        self.order: list[str] = []
        self.checks: list[bool] = []
        self._writable = writable

    @property
    def location(self) -> str:
        return "memoria"

    def ensure_writable(self, overwrite: bool = False) -> None:
        self.checks.append(overwrite)
        if not self._writable:
            raise OutputNotEmptyError(self.location, "el sink de prueba dice que no")

    def write(self, path: str, content: str) -> None:
        self.files[path] = content
        self.order.append(path)


@pytest.fixture
def export_dir(fixtures_dir: Path, tmp_path: Path) -> Path:
    """Export sintético con memorias y conversaciones bajo una raíz con espacios y acentos."""
    root = tmp_path / "export con acentós y espacios"
    root.mkdir()
    shutil.copytree(fixtures_dir / "memories-batched" / "memories-000", root / "memories-000")
    shutil.copytree(
        fixtures_dir / "conversations-batched" / "conversations-000", root / "conversations-000"
    )
    write_manifest(root, {"conversations": [0], "memories": [0]}, created_at=EXPORT_CREATED_AT)
    return root


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return tmp_path / "salida"


@pytest.fixture
def result(export_dir: Path, out: Path) -> ConvertResult:
    return convert(FolderSource(export_dir), FilesystemSink(out))


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------------ el árbol


def test_writes_memories_conversations_index_readme_and_report(
    result: ConvertResult, out: Path
) -> None:
    """CLAUDE.md §5, en lo que hay implementado (M1: sin projects/, frames/ ni account/)."""
    written = set(tree(out))

    assert {"README.md", "_index.md"} <= written
    assert {
        "_report/summary.json",
        "_report/errors.jsonl",
        "_report/inventory.json",
    } <= written
    assert "memories/profile.md" in written
    assert "conversations/2026/01/2026-01-15_analisis-nandu-q3_a1a1a1a1.md" in written
    assert result.destination == str(out)


def test_the_result_counts_what_it_converted(result: ConvertResult, out: Path) -> None:
    assert result.report.counts == {"conversations": 4, "memories": 6}
    assert set(result.files) == set(tree(out))


def test_m1_does_not_invent_the_categories_that_still_have_no_parser(
    result: ConvertResult, out: Path
) -> None:
    """`projects/`, `frames/` y `account/` llegan en M2: no se crean vacías."""
    assert not (out / "projects").exists()
    assert not (out / "frames").exists()
    assert not (out / "account").exists()


# ------------------------------------------------------------------ CA-7 índice


def conversation_rows(out: Path) -> list[str]:
    return [line for line in read(out / "_index.md").splitlines() if "](conversations/" in line]


def test_ca7_index_lists_every_conversation_newest_first(result: ConvertResult, out: Path) -> None:
    index = read(out / "_index.md")
    days = [row.split("|")[1].strip() for row in conversation_rows(out)]

    assert days == ["2026-03-02", "2026-02-03", "2026-01-15", "—"]
    # La conversación sin fecha va al final, no se le inventa una.
    assert index.index("Charla sin fecha") > index.index("Analisis Nandu / Q3")


def test_ca7_index_shows_project_and_message_count(out: Path, result: ConvertResult) -> None:
    row = next(
        line for line in read(out / "_index.md").splitlines() if "2026-01-15_analisis" in line
    )
    cells = [cell.strip() for cell in row.split("|")[1:-1]]

    assert cells[0] == "2026-01-15"
    assert "Analisis Nandu / Q3" in cells[1]
    assert cells[3] == "2"  # dos mensajes


def test_ca7_index_links_are_relative_and_resolve(out: Path, result: ConvertResult) -> None:
    links = [
        line.split("](")[1].split(")")[0]
        for line in read(out / "_index.md").splitlines()
        if "](" in line
    ]

    assert links
    for link in links:
        assert not link.startswith(("/", "http"))
        assert (out / link).is_file()


def test_the_index_also_lists_the_memories(out: Path, result: ConvertResult) -> None:
    index = read(out / "_index.md")

    assert "memories/profile.md" in index
    assert "Memoria de conversaciones" in index


def test_a_title_with_a_pipe_does_not_break_the_index_table(tmp_path: Path) -> None:
    """Un `|` en el título del usuario partiría la fila en dos celdas si no se escapa."""
    root = tmp_path / "export"
    (root / "conversations-000").mkdir(parents=True)
    (root / "conversations-000" / "conversations.json").write_text(
        json.dumps(
            [
                {
                    "uuid": "11111111-1111-4111-8111-111111111111",
                    "name": "Ventas | Q3 [borrador]",
                    "created_at": "2026-01-02T10:00:00.000000Z",
                    "chat_messages": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "salida"

    convert(FolderSource(root), FilesystemSink(out))
    row = next(line for line in read(out / "_index.md").splitlines() if "Ventas" in line)

    # 4 columnas → 5 barras de tabla; la del título va escapada y no cuenta.
    assert row.count("|") - row.count(r"\|") == 5
    assert r"Ventas \| Q3 \[borrador\]" in row


# --------------------------------------------------------- CA-8 informe


def test_ca8_summary_has_counts_per_category_and_the_number_of_errors(
    result: ConvertResult, out: Path
) -> None:
    summary = json.loads(read(out / "_report" / "summary.json"))

    assert summary["categories"] == {"conversations": 4, "memories": 6}
    assert summary["error_count"] == len(result.report.errors) == 3
    assert summary["errors_file"] == "_report/errors.jsonl"
    assert summary["export_created_at"] == "2026-09-18T16:59:47Z"


def test_ca8_errors_jsonl_has_one_line_per_parse_error(result: ConvertResult, out: Path) -> None:
    lines = read(out / "_report" / "errors.jsonl").splitlines()

    assert len(lines) == len(result.report.errors)
    assert {json.loads(line)["category"] for line in lines} == {"conversations"}
    assert all("reason" in json.loads(line) for line in lines)


def test_errors_jsonl_exists_even_without_errors(tmp_path: Path, fixtures_dir: Path) -> None:
    out = tmp_path / "salida"
    convert(FolderSource(fixtures_dir / "memories-batched"), FilesystemSink(out))

    assert (out / "_report" / "errors.jsonl").read_text(encoding="utf-8") == ""


def test_a_corrupt_item_does_not_stop_the_run(result: ConvertResult, out: Path) -> None:
    """CLAUDE.md §1.3: el ítem sin `uuid` se registra y las 4 conversaciones válidas salen."""
    reasons = [error.reason for error in result.report.errors]

    assert any("conversación sin `uuid`" in reason for reason in reasons)
    assert (
        len([path for path in tree(out) if path.endswith(".md") and "conversations/" in path]) == 4
    )


def test_the_summary_keeps_the_warnings_of_the_run(result: ConvertResult, out: Path) -> None:
    summary = json.loads(read(out / "_report" / "summary.json"))

    assert summary["warning_count"] == len(result.report.warnings)
    assert any("frames" in warning for warning in summary["warnings"])


# ------------------------------------------------------------------ README


def test_the_readme_shows_the_export_date_not_the_run_date(
    result: ConvertResult, out: Path
) -> None:
    readme = read(out / "README.md")

    assert "2026-09-18T16:59:47Z" in readme
    assert result.export_created_at == "2026-09-18T16:59:47Z"


def test_a_broken_manifest_does_not_stop_the_conversion(export_dir: Path, out: Path) -> None:
    """Un manifiesto ilegible es una advertencia: la conversión sigue, pero sin fecha."""
    next(export_dir.glob("member-manifest-*.json")).write_text("{ roto", encoding="utf-8")

    outcome = convert(FolderSource(export_dir), FilesystemSink(out))

    assert outcome.export_created_at is None
    assert outcome.counts == {"conversations": 4, "memories": 6}
    assert any("manifiesto" in warning for warning in outcome.report.warnings)


def test_the_result_answers_what_the_caller_needs(result: ConvertResult, out: Path) -> None:
    """Lo que el CLI y la API leen del resultado, sin volver a mirar el disco."""
    assert result.counts == {"conversations": 4, "memories": 6}
    assert result.error_count == 3
    assert result.warning_count == len(result.report.warnings)
    # Relativa al sink, no absoluta: un ZipSink no tiene rutas de disco (ADR-0006).
    assert result.errors_file == "_report/errors.jsonl"
    assert (out / result.errors_file).is_file()


def test_the_readme_works_without_manifest(tmp_path: Path, fixtures_dir: Path) -> None:
    """Sin manifiesto no hay fecha del export: se omite, nunca se usa la del reloj."""
    out = tmp_path / "salida"
    outcome = convert(FolderSource(fixtures_dir / "memories-batched"), FilesystemSink(out))

    assert outcome.export_created_at is None
    assert "Fecha del export" not in read(out / "README.md")


# ------------------------------------------------------ determinismo (CA-1)


def test_ca1_two_runs_produce_the_same_bytes(export_dir: Path, tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"

    convert(FolderSource(export_dir), FilesystemSink(first))
    convert(FolderSource(export_dir), FilesystemSink(second))

    assert tree(first) == tree(second)


def test_rerunning_over_the_same_folder_is_idempotent(export_dir: Path, out: Path) -> None:
    convert(FolderSource(export_dir), FilesystemSink(out))
    before = tree(out)

    convert(FolderSource(export_dir), FilesystemSink(out), overwrite=True)

    assert tree(out) == before


def test_everything_written_is_utf8_and_lf(result: ConvertResult, out: Path) -> None:
    for content in tree(out).values():
        assert b"\r\n" not in content
    assert "Ñandú" in read(out / "memories" / "areas" / "analisis-nandu.md")


# ------------------------------------------------- salida no vacía y formato


def test_a_non_empty_output_without_overwrite_touches_nothing(export_dir: Path, out: Path) -> None:
    """Spec 05 CA-3: se aborta antes de escribir un solo byte."""
    out.mkdir(parents=True)
    (out / "lo-que-ya-estaba.md").write_text("mío", encoding="utf-8")

    with pytest.raises(OutputNotEmptyError):
        convert(FolderSource(export_dir), FilesystemSink(out))

    assert tree(out) == {"lo-que-ya-estaba.md": "mío".encode()}


def test_overwrite_allows_writing_into_a_non_empty_output(export_dir: Path, out: Path) -> None:
    out.mkdir(parents=True)
    (out / "lo-que-ya-estaba.md").write_text("mío", encoding="utf-8")

    convert(FolderSource(export_dir), FilesystemSink(out), overwrite=True)

    assert (out / "_index.md").is_file()
    # `--overwrite` sobrescribe lo que se regenera; no borra la carpeta del usuario.
    assert (out / "lo-que-ya-estaba.md").is_file()


def test_an_output_that_is_a_file_is_rejected(export_dir: Path, tmp_path: Path) -> None:
    target = tmp_path / "salida.md"
    target.write_text("no soy una carpeta", encoding="utf-8")

    with pytest.raises(OutputNotEmptyError):
        convert(FolderSource(export_dir), FilesystemSink(target))


def test_an_unrecognised_export_raises_unknown_format(tmp_path: Path) -> None:
    empty = tmp_path / "vacio"
    empty.mkdir()

    with pytest.raises(UnknownFormatError):
        convert(FolderSource(empty), FilesystemSink(tmp_path / "salida"))


# ------------------------------------------------------------------ extras


def test_progress_reports_each_category(export_dir: Path, out: Path) -> None:
    seen: list[tuple[str, int]] = []

    convert(
        FolderSource(export_dir),
        FilesystemSink(out),
        progress=lambda category, done: seen.append((category, done)),
    )

    assert ("memories", 6) in seen
    assert ("conversations", 4) in seen


def test_ca9_a_user_template_replaces_the_default_one(
    export_dir: Path, out: Path, tmp_path: Path
) -> None:
    templates = tmp_path / "mis-plantillas"
    templates.mkdir()
    (templates / "memory.md.j2").write_text("---\nid: {{ id }}\n---\n\nMÍO\n", encoding="utf-8")

    convert(FolderSource(export_dir), FilesystemSink(out), templates=templates)

    assert read(out / "memories" / "profile.md").endswith("MÍO\n")
    # Las demás plantillas siguen viniendo de la librería.
    assert "👤 Usuario" in read(
        out / "conversations/2026/01/2026-01-15_analisis-nandu-q3_a1a1a1a1.md"
    )


# --------------------------------------------- el puerto MarkdownSink (ADR-0006)


def test_convert_writes_only_through_the_sink_port(export_dir: Path, tmp_path: Path) -> None:
    """Hexagonal: el caso de uso se orquesta entero sin que exista un disco."""
    sink = RecordingSink()

    result = convert(FolderSource(export_dir), sink)

    assert isinstance(sink, MarkdownSink)
    assert result.destination == "memoria"
    assert set(result.files) == set(sink.files)
    assert "memories/profile.md" in sink.files
    assert "conversations/2026/01/2026-01-15_analisis-nandu-q3_a1a1a1a1.md" in sink.files
    assert "_index.md" in sink.files
    # Nada tocó el sistema de archivos: la única carpeta que hay es la del export.
    assert [child.name for child in tmp_path.iterdir()] == [export_dir.name]


def test_the_sink_paths_are_relative_and_posix(export_dir: Path) -> None:
    sink = RecordingSink()

    convert(FolderSource(export_dir), sink)

    for path in sink.files:
        assert not path.startswith(("/", "\\"))
        assert "\\" not in path


def test_the_sink_is_asked_before_a_single_byte_is_written(export_dir: Path) -> None:
    """Spec 05 CA-3: si el destino dice que no, no se escribe nada."""
    sink = RecordingSink(writable=False)

    with pytest.raises(OutputNotEmptyError):
        convert(FolderSource(export_dir), sink)

    assert sink.files == {}


def test_overwrite_is_what_the_sink_receives(export_dir: Path) -> None:
    sink = RecordingSink()

    convert(FolderSource(export_dir), sink, overwrite=True)

    assert sink.checks == [True]


def test_nothing_is_written_twice_to_the_same_path(export_dir: Path) -> None:
    """Dos escrituras a la misma ruta serían un archivo perdido (CLAUDE.md §1.3)."""
    sink = RecordingSink()

    convert(FolderSource(export_dir), sink)

    assert len(sink.order) == len(set(sink.order))


# -------------------------------------- colisión de rutas de conversación


#: Dos uuids con los MISMOS 8 primeros caracteres alfanuméricos: mismo día y mismo
#: título dan la misma ruta de salida.
TWINS = json.dumps(
    [
        {
            "uuid": f"a1a1a1a1-0000-4000-8000-00000000000{n}",
            "name": "Ventas",
            "created_at": "2026-01-15T10:00:00.000000Z",
            "chat_messages": [{"uuid": f"m{n}", "sender": "human", "text": f"mensaje {n}"}],
        }
        for n in (1, 2)
    ]
)


@pytest.fixture
def twins_export(tmp_path: Path) -> Path:
    root = tmp_path / "gemelas"
    (root / "conversations-000").mkdir(parents=True)
    (root / "conversations-000" / "conversations.json").write_text(TWINS, encoding="utf-8")
    return root


def test_two_colliding_conversations_produce_two_files(twins_export: Path, out: Path) -> None:
    """Ninguna de las dos se pierde: la segunda lleva sufijo de desempate."""
    convert(FolderSource(twins_export), FilesystemSink(out))
    written = [path for path in tree(out) if path.startswith("conversations/")]

    assert len(written) == 2
    assert "conversations/2026/01/2026-01-15_ventas_a1a1a1a1.md" in written
    bodies = [read(out / path) for path in written]
    assert any("mensaje 1" in body for body in bodies)
    assert any("mensaje 2" in body for body in bodies)


def test_a_colliding_conversation_leaves_a_warning_in_the_report(
    twins_export: Path, out: Path
) -> None:
    """CLAUDE.md §1.3: desambiguar en silencio tampoco vale; queda dicho."""
    result = convert(FolderSource(twins_export), FilesystemSink(out))
    summary = json.loads(read(out / "_report" / "summary.json"))

    collisions = [w for w in result.report.warnings if "querían escribir" in w]
    assert len(collisions) == 1
    assert collisions[0] in summary["warnings"]


def test_the_index_points_at_the_disambiguated_file(twins_export: Path, out: Path) -> None:
    """La fila del índice y el archivo escrito tienen que ser el mismo (CA-7)."""
    convert(FolderSource(twins_export), FilesystemSink(out))
    links = [
        line.split("](")[1].split(")")[0]
        for line in read(out / "_index.md").splitlines()
        if "](conversations/" in line
    ]

    assert len(links) == len(set(links)) == 2
    for link in links:
        assert (out / link).is_file()


def test_the_collision_is_resolved_the_same_way_on_every_run(
    twins_export: Path, tmp_path: Path
) -> None:
    """CA-1: el desempate es estable, no depende de la corrida."""
    first, second = tmp_path / "a", tmp_path / "b"

    convert(FolderSource(twins_export), FilesystemSink(first))
    convert(FolderSource(twins_export), FilesystemSink(second))

    assert tree(first) == tree(second)
