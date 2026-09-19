"""Render Markdown de `frames` → `frames/<slug>.md`.

Spec 04 (CA-1 determinismo, CA-2 frontmatter, CA-6 slug, CA-9 plantillas, CA-10 nada de
la corrida) y spec 03 `frames` CA-2 (el contenido real del artefacto NO está en el
export: hay que DECIRLO, nunca dejar un bloque vacío en silencio) y CA-3 (versiones y
versión activa, tolerando que `active_version` no coincida con ninguna).

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

from claude_export_md.domain.entities import Frame, FrameVersion
from claude_export_md.rendering.render import (
    FRAME_CONTENT_UNAVAILABLE,
    FRAME_PAYLOAD_AVAILABLE,
    FRAMES_DIR,
    UNTITLED_FRAME,
    assign_frame_paths,
    build_environment,
    frame_created_at,
    frame_output_path,
    frame_tags,
    frame_title,
    render_frame,
    render_frames,
)

FRAME_1 = "f1f1f1f1-1111-4222-8333-444444444444"
FRAME_2 = "f2f2f2f2-5555-4666-8777-888888888888"
ACCOUNT = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
VERSION_1 = "ver_00000000001"
VERSION_2 = "ver_00000000002"

CREATED = "2026-01-02T03:04:05Z"
CREATED_LATER = "2026-01-09T10:11:12Z"
UPDATED = "2026-02-03T04:05:06Z"


def make_version(**values: Any) -> FrameVersion:
    return FrameVersion.model_validate(
        {
            "id": VERSION_1,
            "title": "Informe de ventas Q3",
            "description": "Un documento con el resumen de ventas del trimestre.",
            "created_at": CREATED,
            **values,
        }
    )


def make_frame(**values: Any) -> Frame:
    frame_id = values.get("id", FRAME_1)
    versions = values.pop("versions", [make_version()])
    payload = values.pop("payload", {"id": frame_id, "kind": "document"})
    return Frame.model_validate(
        {
            "id": FRAME_1,
            "kind": "document",
            "visibility": "private",
            "owner_account": ACCOUNT,
            "updated_at": UPDATED,
            "active_version": VERSION_1,
            "versions": versions,
            "payload": payload,
            "source_file": f"frames-000/artifacts/{frame_id}/{frame_id}.json",
            **values,
        }
    )


@pytest.fixture
def frame() -> Frame:
    return make_frame()


def meta(markdown: str) -> dict[str, Any]:
    """Frontmatter ya parseado. `python-frontmatter` tipa los valores como `object`."""
    return cast(dict[str, Any], frontmatter.loads(markdown).metadata)


# --------------------------------------------------------- CA-2 frontmatter


def test_ca2_frontmatter_has_the_required_fields(frame: Frame) -> None:
    """CA-2: parseable con `python-frontmatter` y con los campos obligatorios."""
    metadata = meta(render_frame(frame))

    assert set(metadata) >= {
        "id",
        "type",
        "title",
        "created_at",
        "updated_at",
        "source_file",
        "tags",
    }
    assert metadata["type"] == "frame"
    assert metadata["id"] == FRAME_1
    assert metadata["updated_at"] == UPDATED
    assert metadata["source_file"] == f"frames-000/artifacts/{FRAME_1}/{FRAME_1}.json"


def test_the_frontmatter_shows_what_kind_of_artifact_it_is(frame: Frame) -> None:
    """`kind` y `visibility` son lo único que el export dice del artefacto en sí."""
    metadata = meta(render_frame(frame))

    assert metadata["kind"] == "document"
    assert metadata["visibility"] == "private"
    assert metadata["version_count"] == 1


def test_unknown_fields_are_visible_under_extra() -> None:
    markdown = render_frame(make_frame(color="azul"))

    metadata = meta(markdown)

    assert metadata["extra"]["color"] == "azul"
    assert "source_file" not in metadata["extra"]
    # `payload` es el JSON íntegro (CA-2), no un campo desconocido: no se duplica ahí.
    assert "payload" not in metadata["extra"]


def test_an_awkward_title_does_not_break_the_yaml() -> None:
    """Un título con `:`, comillas y saltos de línea sigue siendo YAML válido."""
    markdown = render_frame(make_frame(versions=[make_version(title='a: "b"\nc')]))

    assert meta(markdown)["title"] == 'a: "b"\nc'


def test_the_tags_say_it_is_a_frame_and_of_what_kind(frame: Frame) -> None:
    assert frame_tags(frame) == ["frame", "document"]
    assert frame_tags(make_frame(kind=None)) == ["frame"]


# ------------------------------------------------------------------ título


def test_the_title_is_the_one_of_the_active_version() -> None:
    """El artefacto no tiene título propio: lo pone la versión que está activa (CA-3)."""
    frame = make_frame(
        versions=[make_version(), make_version(id=VERSION_2, title="Segunda")],
        active_version=VERSION_2,
    )

    assert frame_title(frame) == "Segunda"


def test_when_the_active_version_matches_nothing_the_title_comes_from_any_version() -> None:
    """CA-3: `active_version` puede no coincidir; aun así hay un título legible que usar."""
    frame = make_frame(active_version="ver_99999999999")

    assert frame_title(frame) == "Informe de ventas Q3"


def test_a_frame_without_titles_falls_back_to_its_kind() -> None:
    """`kind` es lo que el export dice que es el artefacto: mejor eso que inventar."""
    frame = make_frame(versions=[make_version(title=None)])

    assert frame_title(frame) == "document"


def test_a_frame_without_titles_and_without_kind_says_it_has_no_title() -> None:
    frame = make_frame(versions=[], kind=None, active_version=None)

    assert frame_title(frame) == UNTITLED_FRAME


# --------------------------------------------------------- fecha de creación


def test_the_creation_date_is_derived_from_the_oldest_version() -> None:
    """El artefacto no trae `created_at`: se deriva de `versions[]`, no se inventa."""
    frame = make_frame(
        versions=[
            make_version(id=VERSION_2, created_at=CREATED_LATER),
            make_version(created_at=CREATED),
        ]
    )

    assert frame_created_at(frame) == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert meta(render_frame(frame))["created_at"] == CREATED


def test_a_frame_whose_versions_have_no_date_leaves_the_creation_date_empty() -> None:
    """Sin ninguna fecha en `versions[]` el campo va en null, nunca con el reloj (CA-10)."""
    frame = make_frame(versions=[make_version(created_at=None)])

    assert frame_created_at(frame) is None
    assert meta(render_frame(frame))["created_at"] is None


# -------------------------------------------------------------- rutas (CA-6)


def test_each_frame_gets_a_file_named_after_its_active_version(frame: Frame) -> None:
    """CLAUDE.md §5: `frames/<slug>.md` (la categoría ya no es "por investigar")."""
    assert frame_output_path(frame) == f"{FRAMES_DIR}/informe-de-ventas-q3.md"


def test_a_frame_without_titles_uses_the_slug_of_its_kind() -> None:
    frame = make_frame(versions=[make_version(title=None)])

    assert frame_output_path(frame) == f"{FRAMES_DIR}/document.md"


def test_two_frames_whose_title_slugifies_the_same_never_share_a_file() -> None:
    """Dos títulos distintos pueden dar el mismo slug; ninguno puede pisar al otro."""
    frames = [
        make_frame(versions=[make_version(title="Q3: Ventas")]),
        make_frame(id=FRAME_2, versions=[make_version(title="Q3 / Ventas")]),
    ]

    paths = [path for _frame, path in assign_frame_paths(frames)]

    assert len(set(paths)) == 2
    assert all(path.startswith(f"{FRAMES_DIR}/q3-ventas-") for path in paths)


def test_the_file_of_each_frame_does_not_depend_on_the_order() -> None:
    """Mismo criterio que memorias y proyectos: el desempate depende del `id`."""
    frames = [
        make_frame(versions=[make_version(title="Q3: Ventas")]),
        make_frame(id=FRAME_2, versions=[make_version(title="Q3 / Ventas")]),
    ]

    def by_id(pairs: list[tuple[Frame, str]]) -> dict[str, str]:
        return {frame.id: path for frame, path in pairs}

    assert by_id(assign_frame_paths(frames)) == by_id(assign_frame_paths(list(reversed(frames))))


# ------------------------------------- CA-2 el contenido no está en el export


def test_ca2_the_file_says_explicitly_that_the_content_is_not_in_the_export(
    frame: Frame,
) -> None:
    """Spec 03 `frames` CA-2: nunca un bloque vacío en silencio ni contenido inventado."""
    markdown = render_frame(frame)

    assert FRAME_CONTENT_UNAVAILABLE in markdown
    assert "## Contenido" in markdown


def test_ca2_the_notice_is_the_same_criterion_used_for_a_project_doc() -> None:
    """La frase dice qué falta y que no se inventó nada (como `DOC_CONTENT_UNAVAILABLE`)."""
    assert "no incluye el contenido" in FRAME_CONTENT_UNAVAILABLE
    assert "No se ha inventado" in FRAME_CONTENT_UNAVAILABLE


def test_ca2_the_whole_original_json_is_visible_in_the_file() -> None:
    """CA-2: el payload íntegro queda a la vista, para no perder nada mientras se busca."""
    markdown = render_frame(make_frame(payload={"id": FRAME_1, "misterio": "sin identificar"}))

    assert "misterio" in markdown
    assert "sin identificar" in markdown


def test_a_frame_without_payload_does_not_print_an_empty_json_block() -> None:
    """Sin JSON que enseñar no se imprime la sección ni se promete lo que no hay."""
    markdown = render_frame(make_frame(payload={}))

    assert "## JSON original" not in markdown
    assert FRAME_PAYLOAD_AVAILABLE not in markdown
    assert FRAME_CONTENT_UNAVAILABLE in markdown


# ----------------------------------------------------- CA-3 versiones


def test_ca3_every_version_is_listed_with_its_metadata() -> None:
    frame = make_frame(
        versions=[make_version(), make_version(id=VERSION_2, title="Segunda", description="Otra.")],
        active_version=VERSION_2,
    )

    markdown = render_frame(frame)

    assert VERSION_1 in markdown
    assert VERSION_2 in markdown
    assert "Informe de ventas Q3" in markdown
    assert "Segunda" in markdown
    assert "Otra." in markdown


def test_ca3_the_active_version_shows_its_description_as_text(frame: Frame) -> None:
    markdown = render_frame(frame)

    assert "## Versión activa" in markdown
    assert "Un documento con el resumen de ventas del trimestre." in markdown


def test_ca3_an_active_version_that_matches_nothing_is_said_out_loud() -> None:
    """CA-3: se tolera, pero el `.md` lo cuenta en vez de callarse la incoherencia."""
    markdown = render_frame(make_frame(active_version="ver_99999999999"))

    assert "ver_99999999999" in markdown
    assert "no coincide" in markdown


def test_a_frame_without_active_version_says_so_instead_of_leaving_a_mute_section() -> None:
    markdown = render_frame(make_frame(active_version=None))

    assert "## Versión activa" in markdown
    assert "no dice cuál" in markdown


def test_a_frame_without_versions_says_so_instead_of_leaving_an_empty_section() -> None:
    markdown = render_frame(make_frame(versions=[], active_version=None))

    assert "## Versiones" in markdown
    assert "ninguna versión" in markdown


# ----------------------------------------------- CA-10 nada de la corrida


def test_ca10_output_has_no_generation_date_or_tool_version(frame: Frame) -> None:
    markdown = render_frame(frame)
    today = datetime.now(tz=UTC).date().isoformat()

    assert today not in markdown
    assert "claude_export_md" not in markdown
    assert "0.1.0" not in markdown


# ------------------------------------------------------ CA-1 determinismo


def test_ca1_two_renders_are_byte_identical() -> None:
    frames = [make_frame(), make_frame(id=FRAME_2, versions=[make_version(title="Otro")])]

    first = render_frames(frames)
    second = render_frames(frames)

    assert first == second
    assert [markdown.encode("utf-8") for _path, markdown in first] == [
        markdown.encode("utf-8") for _path, markdown in second
    ]


def test_render_frames_returns_one_file_per_frame() -> None:
    rendered = render_frames([make_frame(), make_frame(id=FRAME_2)])

    assert len(rendered) == 2
    assert all(path.endswith(".md") for path, _markdown in rendered)


# --------------------------------------------------------- CA-9 plantillas


def test_ca9_user_template_overrides_the_default(tmp_path: Path, frame: Frame) -> None:
    (tmp_path / "frame.md.j2").write_text("MÍO: {{ title }}\n", encoding="utf-8")

    assert render_frame(frame, build_environment(tmp_path)) == "MÍO: Informe de ventas Q3\n"


# ------------------------------------------------------------------ snapshot


def test_snapshot_of_a_frame_with_several_versions(snapshot: SnapshotAssertion) -> None:
    frames = [
        make_frame(
            versions=[
                make_version(),
                make_version(id=VERSION_2, title="Informe de ventas Q3 (v2)"),
            ],
            active_version=VERSION_2,
            payload={
                "id": FRAME_1,
                "kind": "document",
                "visibility": "private",
                "versions": [{"id": VERSION_1}, {"id": VERSION_2}],
            },
        ),
        make_frame(id=FRAME_2, versions=[], active_version="ver_99999999999", payload={}),
    ]

    assert dict(render_frames(frames)) == snapshot
