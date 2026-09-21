"""Render Markdown de `memories` (spec 04, CA-1, CA-2, CA-6, CA-9, CA-10).

El snapshot (`syrupy`) es la red de seguridad del formato: si cambia una línea del
Markdown generado, el test falla y hay que mirar el diff a ojo antes de actualizarlo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import frontmatter
import pytest
from syrupy.assertion import SnapshotAssertion

from claude_export_md.adapters.parsers import memories as parser
from claude_export_md.adapters.source_folder import FolderSource
from claude_export_md.domain.entities import (
    Memory,
    Report,
    conversations_memory,
    memory_from_file,
    project_memory,
)
from claude_export_md.rendering.filters import iso_utc, slugify
from claude_export_md.rendering.render import (
    assign_output_paths,
    build_environment,
    memory_output_path,
    memory_title,
    render_memory,
)

PROJECT = "ffffffff-0000-4000-8000-000000000001"


@pytest.fixture
def memories(fixtures_dir: Path) -> list[Memory]:
    return list(parser.parse(FolderSource(fixtures_dir / "memories-batched"), Report()))


def rendered(memories: list[Memory]) -> dict[str, str]:
    environment = build_environment()
    return {memory.path: render_memory(memory, environment) for memory in memories}


def meta(markdown: str) -> dict[str, Any]:
    """Frontmatter ya parseado. `python-frontmatter` tipa los valores como `object`."""
    return cast(dict[str, Any], frontmatter.loads(markdown).metadata)


# ------------------------------------------------------------- CA-6 slugify


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Análisis Ñandú / Q3", "analisis-nandu-q3"),
        ("  guiones   y  espacios  ", "guiones-y-espacios"),
        ("Ya-slug-ificado", "ya-slug-ificado"),
        ("¿Qué? ¡Ojo!", "que-ojo"),
        ("日本語", "sin-titulo"),
        ("", "sin-titulo"),
    ],
)
def test_ca6_slugify(value: str, expected: str) -> None:
    """CA-6: ASCII, minúsculas, sin caracteres especiales."""
    assert slugify(value) == expected


def test_slug_is_capped_and_never_cut_mid_word() -> None:
    slug = slugify("palabras " * 20)

    assert len(slug) <= 60
    assert not slug.endswith("-")
    assert slug.split("-")[-1] == "palabras"


def test_a_single_word_longer_than_the_cap_is_cut_anyway() -> None:
    """Si no hay dónde cortar por palabra, se corta por longitud: siempre hay nombre."""
    slug = slugify("a" * 80)

    assert slug == "a" * 60


def test_iso_utc_uses_the_z_suffix_without_microseconds() -> None:
    """Spec 04: fechas ISO-8601 UTC como `2026-09-18T16:59:47Z`."""
    assert iso_utc(datetime(2026, 9, 18, 16, 59, 47, 123456, tzinfo=UTC)) == "2026-09-18T16:59:47Z"
    assert iso_utc(None) is None


def test_a_date_inside_extra_is_rendered_as_iso_utc() -> None:
    """Una fecha desconocida en `extra` también sale en ISO-8601 UTC, no como objeto."""
    memory = memory_from_file(
        {"path": "/profile.md", "content": "x", "seen_at": datetime(2026, 3, 4, 5, 6, tzinfo=UTC)}
    )

    assert meta(render_memory(memory))["extra"]["seen_at"] == "2026-03-04T05:06:00Z"


# ------------------------------------------------------- nombres de archivo


def test_output_path_follows_the_memory_path(memories: list[Memory]) -> None:
    """La jerarquía de `Memory.path` se conserva, slugificada segmento a segmento."""
    paths = {memory.path: memory_output_path(memory) for memory in memories}

    assert paths["/profile.md"] == "memories/profile.md"
    assert paths["/people/Ana Maria.md"] == "memories/people/ana-maria.md"
    assert paths["/areas/Analisis Ñandú.md"] == "memories/areas/analisis-nandu.md"


def test_synthetic_paths_produce_readable_file_names(memories: list[Memory]) -> None:
    """ADR-0005: el `_` de la ruta sintética no llega al nombre del archivo."""
    paths = {memory.path: memory_output_path(memory) for memory in memories}

    assert paths["/_conversations_memory.md"] == "memories/conversations-memory.md"
    assert paths[f"/_project_memories/{PROJECT}.md"] == f"memories/project-memories/{PROJECT}.md"


def test_colliding_slugs_get_a_stable_suffix() -> None:
    """Dos rutas distintas que slugifican igual no se pisan, y el desempate es estable."""
    pair = [
        memory_from_file({"path": "/people/Ana María.md", "content": "a"}),
        memory_from_file({"path": "/people/ana-maria!.md", "content": "b"}),
    ]

    assigned = dict(assign_output_paths(pair))
    reversed_order = dict(assign_output_paths(list(reversed(pair))))

    assert len(set(assigned.values())) == 2
    assert assigned == reversed_order


def test_memory_without_usable_path_still_gets_a_name() -> None:
    assert memory_output_path(Memory(path="/···.md")) == "memories/sin-titulo.md"


# ----------------------------------------------------------------- títulos


def test_title_of_a_real_path_is_its_last_segment() -> None:
    """No hay `title` en el export: el último segmento de la ruta es lo más honesto."""
    assert memory_title(memory_from_file({"path": "/people/Ana María.md"})) == "Ana María"
    assert memory_title(memory_from_file({"path": "/profile.md"})) == "profile"


def test_title_keeps_an_extension_that_is_not_of_text() -> None:
    """Solo se quita `.md`/`.txt`: `notas.v2` es el nombre entero, no `notas`."""
    assert memory_title(memory_from_file({"path": "/areas/notas.v2"})) == "notas.v2"


def test_titles_of_the_synthetic_memories_say_what_they_are() -> None:
    assert memory_title(conversations_memory("x")) == "Memoria de conversaciones"
    assert memory_title(project_memory(PROJECT, "x")) == f"Memoria del proyecto {PROJECT}"


# ------------------------------------------------------------ CA-2 frontmatter


def test_ca2_frontmatter_is_valid_and_has_the_required_fields(memories: list[Memory]) -> None:
    """CA-2: parseable con `python-frontmatter` y con los campos obligatorios."""
    for markdown in rendered(memories).values():
        metadata = meta(markdown)

        assert set(metadata) >= {
            "id",
            "type",
            "title",
            "created_at",
            "updated_at",
            "source_file",
            "tags",
        }
        assert metadata["type"] == "memory"


def test_frontmatter_carries_dates_source_and_origin(memories: list[Memory]) -> None:
    metadata = meta(rendered(memories)["/profile.md"])

    assert metadata["id"] == "/profile.md"
    assert metadata["updated_at"] == "2026-01-15T09:30:00Z"
    assert metadata["created_at"] is None  # el export no trae fecha de creación
    assert metadata["source_file"].endswith(".json")
    assert metadata["extra"]["origin"] == "memory_files"
    assert metadata["extra"]["confidence"] == "alta"
    assert "source_file" not in metadata["extra"]


def test_project_memory_frontmatter_links_the_project(memories: list[Memory]) -> None:
    metadata = meta(rendered(memories)[f"/_project_memories/{PROJECT}.md"])

    assert metadata["project_id"] == PROJECT
    assert "project" in metadata["tags"]


def test_memories_of_the_account_have_no_project_id_key(memories: list[Memory]) -> None:
    """`project_id?` es opcional (spec 04): no se emite vacío para no mentir."""
    assert "project_id" not in meta(rendered(memories)["/profile.md"])


def test_tags_describe_the_origin_and_the_folder(memories: list[Memory]) -> None:
    metadata = {path: meta(markdown) for path, markdown in rendered(memories).items()}

    assert metadata["/people/Ana Maria.md"]["tags"] == ["memory", "memory-files", "people"]
    assert metadata["/_conversations_memory.md"]["tags"] == ["memory", "conversations-memory"]


def test_unreadable_date_is_visible_in_the_frontmatter(memories: list[Memory]) -> None:
    """Spec 02 CA-6: el valor original sigue a la vista bajo `extra`."""
    metadata = meta(rendered(memories)["/areas/Analisis Ñandú.md"])

    assert metadata["updated_at"] is None
    assert metadata["extra"]["updated_at_raw"] == "sin fecha"


def test_awkward_title_does_not_break_the_yaml() -> None:
    """Un título con `:`, comillas y saltos de línea sigue siendo YAML válido."""
    memory = memory_from_file({"path": '/raro/a: "b"\nc.md', "content": "hola"})

    post = frontmatter.loads(render_memory(memory, build_environment()))

    assert post.metadata["title"] == 'a: "b"\nc'


# --------------------------------------------------------------- cuerpo


def test_body_is_the_memory_content_verbatim(memories: list[Memory]) -> None:
    """Regla 5 del skill: el texto ya es Markdown, se inserta sin tocarlo."""
    by_path = {memory.path: memory for memory in memories}
    markdown = rendered(memories)["/profile.md"]

    assert by_path["/profile.md"].content.strip() in markdown


def test_body_with_a_horizontal_rule_still_parses(memories: list[Memory]) -> None:
    """Un `---` al inicio de línea del cuerpo no se confunde con el frontmatter."""
    post = frontmatter.loads(rendered(memories)["/areas/Analisis Ñandú.md"])

    assert post.metadata["id"] == "/areas/Analisis Ñandú.md"
    assert "\n---\n" in post.content


def test_empty_memory_renders_only_the_frontmatter() -> None:
    markdown = render_memory(Memory(path="/vacia.md"), build_environment())

    assert frontmatter.loads(markdown).content == ""


# ------------------------------------------------- CA-10 nada de la corrida


def test_ca10_output_has_no_generation_date_or_tool_version(memories: list[Memory]) -> None:
    """CA-10: ni fecha de generación ni versión de la herramienta en el `.md`."""
    today = datetime.now(tz=UTC).date().isoformat()

    for markdown in rendered(memories).values():
        assert today not in markdown
        assert "claude_export_md" not in markdown
        assert "0.1.0" not in markdown


# --------------------------------------------------------- CA-1 determinismo


def test_ca1_two_renders_are_byte_identical(memories: list[Memory]) -> None:
    """CA-1 aplicado a memories: mismo input → mismos bytes."""
    first = rendered(memories)
    second = rendered(memories)

    assert first == second
    assert [m.encode("utf-8") for m in first.values()] == [
        m.encode("utf-8") for m in second.values()
    ]


# ------------------------------------------------------------- CA-9 plantillas

#: Los filtros que la tabla de `docs/specs/04-markdown-output.md` promete al usuario
#: que va a encontrar en CUALQUIER plantilla propia (`--templates`).
DOCUMENTED_FILTERS = (
    "code_fence",
    "hhmm",
    "iso_utc",
    "md_cell",
    "slugify",
    "yaml_block",
    "yaml_inline",
    "yaml_value",
)


def test_every_documented_filter_is_registered() -> None:
    """Spec 04 §Plantillas: lo documentado tiene que existir en el entorno."""
    assert set(DOCUMENTED_FILTERS) <= set(build_environment().filters)


def test_a_user_template_can_use_hhmm_and_code_fence() -> None:
    """Con `StrictUndefined`, un filtro sin registrar sería `TemplateAssertionError`."""
    markdown = (
        build_environment()
        .from_string("{{ t | hhmm }}\n{{ code | code_fence }}")
        .render(t=datetime(2026, 1, 2, 14, 32, tzinfo=UTC), code="print(1)")
    )

    assert markdown == "14:32\n```\nprint(1)\n```"


def test_ca9_user_template_overrides_the_default(tmp_path: Path) -> None:
    """CA-9: una plantilla propia reemplaza a la de la librería."""
    (tmp_path / "memory.md.j2").write_text("MÍA: {{ title }}\n", encoding="utf-8")

    markdown = render_memory(
        memory_from_file({"path": "/profile.md", "content": "x"}),
        build_environment(tmp_path),
    )

    assert markdown == "MÍA: profile\n"


# ------------------------------------------------------------------ snapshot


def test_snapshot_of_every_memory(memories: list[Memory], snapshot: SnapshotAssertion) -> None:
    assert rendered(memories) == snapshot
