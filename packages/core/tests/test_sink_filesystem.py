"""`FilesystemSink`: el adapter que escribe el árbol en disco (spec 04 CA-1, ADR-0006).

El sink no sabe qué está escribiendo: recibe una ruta relativa POSIX y un texto ya
renderizado. Por eso cada test junta aquí el render (`rendering/`) con el sink, que es
lo que hace `usecases/convert.py`, pero sin el resto de la orquestación.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_export_md.adapters.parsers import conversations as conversations_parser
from claude_export_md.adapters.parsers import memories as parser
from claude_export_md.adapters.sink_filesystem import FilesystemSink
from claude_export_md.adapters.source_folder import FolderSource
from claude_export_md.domain.entities import Conversation, Memory, Report, memory_from_file
from claude_export_md.errors import OutputNotEmptyError
from claude_export_md.ports.sink import MarkdownSink
from claude_export_md.rendering.conversations import render_conversations
from claude_export_md.rendering.render import render_memories


def parse_fixture(fixtures_dir: Path) -> list[Memory]:
    return list(parser.parse(FolderSource(fixtures_dir / "memories-batched"), Report()))


def parse_conversations(fixtures_dir: Path) -> list[Conversation]:
    source = FolderSource(fixtures_dir / "conversations-batched")
    return conversations_parser.parse_sorted(source, Report())


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def write_memories(memories: list[Memory], out: Path) -> list[str]:
    """Lo que hace `convert` con las memorias, reducido a render + sink."""
    sink = FilesystemSink(out)
    written: list[str] = []
    for path, markdown in render_memories(memories):
        sink.write(path, markdown)
        written.append(path)
    return written


def write_conversations(conversations: list[Conversation], out: Path) -> list[str]:
    """Ídem con las conversaciones y sus artefactos."""
    sink = FilesystemSink(out)
    written: list[str] = []
    for rendered in render_conversations(conversations):
        sink.write(rendered.path, rendered.markdown)
        written.append(rendered.path)
        for artifact in rendered.artifacts:
            sink.write(artifact.path, artifact.content)
            written.append(artifact.path)
    return written


# ------------------------------------------------------------------ el puerto


def test_the_filesystem_sink_implements_the_port(tmp_path: Path) -> None:
    assert isinstance(FilesystemSink(tmp_path), MarkdownSink)


def test_a_posix_relative_path_lands_inside_the_root(tmp_path: Path) -> None:
    """El sink traduce la ruta POSIX del render a la del sistema de archivos."""
    sink = FilesystemSink(tmp_path / "salida")

    sink.write("conversations/2026/01/charla.md", "hola\n")

    assert (tmp_path / "salida" / "conversations" / "2026" / "01" / "charla.md").is_file()
    assert sink.location == str(tmp_path / "salida")


def test_writing_twice_overwrites_instead_of_appending(tmp_path: Path) -> None:
    sink = FilesystemSink(tmp_path)

    sink.write("a.md", "primero\n")
    sink.write("a.md", "segundo\n")

    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "segundo\n"


# ----------------------------------------------------- CA-3 salida no vacía


def test_a_missing_or_empty_folder_is_writable(tmp_path: Path) -> None:
    FilesystemSink(tmp_path / "no-existe").ensure_writable()
    FilesystemSink(tmp_path).ensure_writable()


def test_a_non_empty_folder_needs_overwrite(tmp_path: Path) -> None:
    (tmp_path / "lo-que-ya-estaba.md").write_text("mío", encoding="utf-8")

    with pytest.raises(OutputNotEmptyError):
        FilesystemSink(tmp_path).ensure_writable()

    FilesystemSink(tmp_path).ensure_writable(overwrite=True)


def test_a_file_where_the_folder_should_be_is_always_rejected(tmp_path: Path) -> None:
    target = tmp_path / "salida.md"
    target.write_text("no soy una carpeta", encoding="utf-8")

    with pytest.raises(OutputNotEmptyError):
        FilesystemSink(target).ensure_writable(overwrite=True)


# ------------------------------------------------------------------ memorias


def test_writes_one_file_per_memory_under_memories(fixtures_dir: Path, tmp_path: Path) -> None:
    write_memories(parse_fixture(fixtures_dir), tmp_path)

    assert sorted(tree(tmp_path)) == [
        "memories/areas/analisis-nandu.md",
        "memories/conversations-memory.md",
        "memories/people/ana-maria.md",
        "memories/profile.md",
        "memories/project-memories/ffffffff-0000-4000-8000-000000000001.md",
        "memories/project-memories/ffffffff-0000-4000-8000-000000000002.md",
    ]


def test_ca1_two_runs_produce_the_same_bytes(fixtures_dir: Path, tmp_path: Path) -> None:
    """CA-1: `diff -r` entre dos salidas del mismo export está vacío."""
    first, second = tmp_path / "a", tmp_path / "b"

    write_memories(parse_fixture(fixtures_dir), first)
    write_memories(parse_fixture(fixtures_dir), second)

    assert tree(first) == tree(second)


def test_rerunning_over_the_same_folder_does_not_duplicate(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    """Idempotencia (CLAUDE.md §1.4): reconvertir sobrescribe, no acumula."""
    memories = parse_fixture(fixtures_dir)

    write_memories(memories, tmp_path)
    before = tree(tmp_path)
    write_memories(memories, tmp_path)

    assert tree(tmp_path) == before


def test_line_endings_are_always_lf(fixtures_dir: Path, tmp_path: Path) -> None:
    """Determinismo entre plataformas: nunca CRLF, tampoco en Windows."""
    write_memories(parse_fixture(fixtures_dir), tmp_path)

    for content in tree(tmp_path).values():
        assert b"\r\n" not in content


def test_content_is_utf8(fixtures_dir: Path, tmp_path: Path) -> None:
    write_memories(parse_fixture(fixtures_dir), tmp_path)
    target = tmp_path / "memories" / "areas" / "analisis-nandu.md"

    assert "Analisis Ñandú" in target.read_text(encoding="utf-8")


def test_nothing_is_written_when_there_are_no_memories(tmp_path: Path) -> None:
    assert write_memories([], tmp_path) == []
    assert not (tmp_path / "memories").exists()


def test_colliding_names_produce_two_files(tmp_path: Path) -> None:
    """Dos memorias distintas nunca se pisan aunque sus rutas slugifiquen igual."""
    written = write_memories(
        [
            memory_from_file({"path": "/people/Ana María.md", "content": "a"}),
            memory_from_file({"path": "/people/ana-maria!.md", "content": "b"}),
        ],
        tmp_path,
    )

    assert len(written) == len(set(written)) == 2
    assert len(tree(tmp_path)) == 2


# ------------------------------------------------------------ conversaciones


def test_conversations_are_written_by_year_and_month(fixtures_dir: Path, tmp_path: Path) -> None:
    """CLAUDE.md §5: `conversations/YYYY/MM/YYYY-MM-DD_<slug>_<uuid8>.md`."""
    write_conversations(parse_conversations(fixtures_dir), tmp_path)

    assert sorted(tree(tmp_path)) == [
        "conversations/2026/01/2026-01-15_analisis-nandu-q3_a1a1a1a1.md",
        "conversations/2026/01/2026-01-15_analisis-nandu-q3_a1a1a1a1/artifacts/01-ventas.py",
        "conversations/2026/02/2026-02-03_sin-titulo_b2b2b2b2.md",
        "conversations/2026/03/2026-03-02_mensajes-con-forma-inesperada_d4d4d4d4.md",
        "conversations/sin-fecha/charla-sin-fecha_c3c3c3c3.md",
    ]


def test_the_artifact_is_written_next_to_its_conversation(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    """CA-5: el enlace relativo del cuerpo tiene que resolver a un archivo real."""
    write_conversations(parse_conversations(fixtures_dir), tmp_path)
    markdown = tmp_path / "conversations/2026/01/2026-01-15_analisis-nandu-q3_a1a1a1a1.md"
    link = "2026-01-15_analisis-nandu-q3_a1a1a1a1/artifacts/01-ventas.py"

    assert f"]({link})" in markdown.read_text(encoding="utf-8")
    assert (markdown.parent / link).is_file()


def test_ca1_two_runs_of_conversations_produce_the_same_bytes(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    first, second = tmp_path / "a", tmp_path / "b"

    write_conversations(parse_conversations(fixtures_dir), first)
    write_conversations(parse_conversations(fixtures_dir), second)

    assert tree(first) == tree(second)


def test_conversation_files_are_utf8_and_lf(fixtures_dir: Path, tmp_path: Path) -> None:
    write_conversations(parse_conversations(fixtures_dir), tmp_path)

    for content in tree(tmp_path).values():
        assert b"\r\n" not in content
    assert "👤 Usuario" in (
        tmp_path / "conversations/sin-fecha/charla-sin-fecha_c3c3c3c3.md"
    ).read_text(encoding="utf-8")


def test_nothing_is_written_when_there_are_no_conversations(tmp_path: Path) -> None:
    assert write_conversations([], tmp_path) == []
    assert not (tmp_path / "conversations").exists()
